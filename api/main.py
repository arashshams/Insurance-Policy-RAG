"""
FastAPI backend for Insurance-Policy-RAG.

Exposes the same retrieval + grounded-generation pipeline (src/rag_pipeline.py)
over HTTP so any client — including the Streamlit app — can ask questions
without importing the pipeline in-process.

Endpoints:
    GET  /health -> service + index + API-key status (no LLM call)
    POST /ask    -> {question, k?} -> grounded answer with page citations

The bundled demo index (app/demo_index/, the SAMPLE-watermarked policy) is the
served corpus, mirroring the Streamlit demo mode. Nothing is persisted per
request; the index is opened once at startup.

Abuse / cost controls (every /ask spends the server's Gemini quota):
  * INSURANCE_RAG_API_TOKEN   if set, /ask requires
                              "Authorization: Bearer <token>" (401 otherwise).
                              Strongly recommended for any public deployment.
  * per-client and global rate limits (429 + Retry-After); see
    src/guardrails.py for the env vars. The client key is the socket peer
    address; behind a reverse proxy that is the proxy, so the per-client limit
    then behaves like a second global limit (still safe, just coarser).
  * questions are capped at MAX_QUESTION_CHARS characters.

Run locally:
    uvicorn api.main:app --reload
    # then: curl -X POST localhost:8000/ask -H 'content-type: application/json' \
    #             -d '{"question": "Is physiotherapy covered?"}'
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

# --- Make src/ importable whether run from repo root or api/ ----------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import guardrails  # noqa: E402 - after sys.path setup
from src.rag_pipeline import (  # noqa: E402 - after sys.path setup
    GEN_MODEL,
    K_DEFAULT,
    GeminiQuotaExhaustedError,
    GeminiUnavailableError,
    answer_question_detailed,
    load_persistent_collection,
)

# Path to the pre-built demo index shipped with the app (same as Streamlit).
DEMO_INDEX_DIR = os.environ.get(
    "DEMO_INDEX_DIR", str(REPO_ROOT / "app" / "demo_index")
)

MAX_QUESTION_CHARS = int(os.environ.get("INSURANCE_RAG_MAX_QUESTION_CHARS", "1000"))

app = FastAPI(
    title="Insurance-Policy-RAG API",
    version="1.1.0",
    description="Grounded, page-cited Q&A over an insurance policy.",
)

# Module-level cache for the opened collection (loaded lazily, once).
_collection = None

# Rate limiters (process-local; per-minute windows).
_client_limiter = guardrails.RateLimiter(guardrails.API_RATE_PER_CLIENT, 60)
_global_limiter = guardrails.RateLimiter(guardrails.API_RATE_GLOBAL, 60)


def _api_key_present() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def _api_token() -> str:
    return os.environ.get("INSURANCE_RAG_API_TOKEN", "").strip()


def _check_auth(authorization: str | None) -> None:
    token = _api_token()
    if not token:
        return
    supplied = ""
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    if not supplied or not secrets.compare_digest(supplied, token):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _check_rate(client_key: str) -> None:
    for limiter, key in ((_client_limiter, client_key), (_global_limiter, "global")):
        ok, retry_after = limiter.allow(key)
        if not ok:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded; try again shortly.",
                headers={"Retry-After": str(max(1, int(retry_after) + 1))},
            )


def _get_collection():
    """Open the demo index once and cache it for the process lifetime."""
    global _collection
    if _collection is None:
        if not os.path.isdir(DEMO_INDEX_DIR):
            raise RuntimeError(
                f"Demo index not found at '{DEMO_INDEX_DIR}'. Build and commit "
                "it (see app/README.md) or set DEMO_INDEX_DIR."
            )
        _collection = load_persistent_collection(persist_dir=DEMO_INDEX_DIR)
    return _collection


# --- Schemas ----------------------------------------------------------------
class AskRequest(BaseModel):
    question: str = Field(
        ..., min_length=1, max_length=MAX_QUESTION_CHARS,
        description="Natural-language question.",
    )
    k: int = Field(K_DEFAULT, ge=1, le=20, description="Number of chunks to retrieve.")


class RetrievedChunk(BaseModel):
    id: str
    page: int | None = None
    score: float | None = None
    text: str


class AskResponse(BaseModel):
    answer: str
    pages: list[int]
    abstained: bool
    citations_verified: bool = Field(
        False,
        description=(
            "True when `pages` come from the passages the model explicitly "
            "cited; False when it cited none and `pages` lists every "
            "retrieved passage instead."
        ),
    )
    retrieved: list[RetrievedChunk]


# --- Endpoints --------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, Any]:
    """Lightweight readiness probe; never calls the LLM."""
    return {
        "status": "ok",
        "index_present": os.path.isdir(DEMO_INDEX_DIR),
        "api_key_present": _api_key_present(),
        "auth_required": bool(_api_token()),
        "model_default": GEN_MODEL,
    }


@app.post("/ask", response_model=AskResponse)
def ask(
    req: AskRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> AskResponse:
    """Answer a question grounded in the bundled policy, cited by page."""
    _check_auth(authorization)
    _check_rate(request.client.host if request.client else "unknown")

    if not _api_key_present():
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not set on the server; cannot generate.",
        )

    try:
        collection = _get_collection()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        result = answer_question_detailed(collection, req.question, k=req.k)
    except GeminiQuotaExhaustedError as exc:
        # Daily quota used up: tell the client when it resets, not "in a minute".
        wait = int(exc.retry_after_s) + 1 if exc.retry_after_s else 3600
        raise HTTPException(
            status_code=503, detail=str(exc), headers={"Retry-After": str(wait)}
        ) from exc
    except GeminiUnavailableError as exc:
        # Gemini overloaded / rate-limited even after the pipeline's retries:
        # a temporary condition, so tell the client to come back later.
        raise HTTPException(
            status_code=503, detail=str(exc), headers={"Retry-After": "60"}
        ) from exc
    except Exception as exc:  # noqa: BLE001 - surface pipeline errors as 502
        raise HTTPException(status_code=502, detail=f"Pipeline error: {exc}") from exc

    chunks = [
        RetrievedChunk(
            id=r.get("id", ""),
            page=r.get("metadata", {}).get("page"),
            score=r.get("score"),
            text=r.get("text", ""),
        )
        for r in result["retrieved"]
    ]

    return AskResponse(
        answer=result["answer"],
        pages=[p for p in result["pages"] if p is not None],
        abstained=result["abstained"],
        citations_verified=result["citations_verified"],
        retrieved=chunks,
    )
