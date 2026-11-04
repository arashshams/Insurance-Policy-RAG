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

import json
import logging
import os
import secrets
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

# --- Make src/ importable whether run from repo root or api/ ----------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import guardrails  # noqa: E402 - after sys.path setup
from src import monitoring  # noqa: E402 - after sys.path setup
from src.rag_pipeline import (  # noqa: E402 - after sys.path setup
    GEN_FALLBACK_MODEL,
    DISTANCE_THRESHOLD,
    GEN_MODEL,
    K_DEFAULT,
    GeminiQuotaExhaustedError,
    GeminiUnavailableError,
    answer_question_detailed,
    load_persistent_collection,
    pipeline_fingerprint,
)

# Path to the pre-built demo index shipped with the app (same as Streamlit).
DEMO_INDEX_DIR = os.environ.get(
    "DEMO_INDEX_DIR", str(REPO_ROOT / "app" / "demo_index")
)

MAX_QUESTION_CHARS = int(os.environ.get("INSURANCE_RAG_MAX_QUESTION_CHARS", "1000"))

log = logging.getLogger("insurance_rag.api")
logging.basicConfig(level=os.environ.get("INSURANCE_RAG_LOG_LEVEL", "INFO"),
                    format="%(levelname)s %(name)s: %(message)s")

# One JSON line per question on stdout. Cloud Run parses it into a structured
# log entry ("severity" and "message" are special fields), so the console can
# filter on any field. Same fields as the metrics record (src/monitoring.py):
# never the question, the answer or the client address.
request_log = logging.getLogger("insurance_rag.requests")
if not request_log.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    request_log.addHandler(_handler)
    request_log.setLevel(logging.INFO)
    request_log.propagate = False

# Version label for metrics: Cloud Run sets K_REVISION on every deploy.
APP_VERSION = os.environ.get("K_REVISION") or os.environ.get("INSURANCE_RAG_VERSION") or "local"
_PIPELINE = pipeline_fingerprint()


def _record_request(*, rid: str, status: int, seconds: float, result: dict | None = None,
                    error: Exception | None = None) -> None:
    """Log one structured line and store one metrics record (best-effort)."""
    event = monitoring.build_event(
        rid=rid, status=status, seconds=seconds, result=result,
        error=type(error).__name__ if error else None,
        pipeline=_PIPELINE, version=APP_VERSION)
    cause = type(error.__cause__).__name__ if error is not None and error.__cause__ else None
    if error is None:
        message = (f"ask ok {event['seconds']:.1f}s model={event['model']}"
                   + (" (fallback)" if event["fallback_used"] else ""))
    else:
        message = f"ask failed {status} {event['error']} cause={cause}"
    request_log.log(logging.INFO if error is None else logging.WARNING, json.dumps({
        "severity": "INFO" if error is None else "WARNING", "message": message,
        **event, "cause": cause}))
    monitoring.record(event)

# Module-level cache for the opened collection (loaded once).
_collection = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Open the demo index at startup, so the first visitor after a cold start
    doesn't also pay for opening it. A failure is logged, not fatal: /health
    stays up and reports index_loaded=false, and /ask retries the load."""
    try:
        _get_collection()
    except Exception as exc:  # noqa: BLE001 - keep the service up for /health
        log.warning("Demo index not loaded at startup: %s", exc)
    yield


app = FastAPI(
    title="Insurance-Policy-RAG API",
    version="1.2.0",
    description="Grounded, page-cited Q&A over an insurance policy.",
    lifespan=_lifespan,
)


@app.middleware("http")
async def _request_id(request: Request, call_next):
    """Echo the caller's X-Request-ID (or a new one) on every response, so a
    reply can be matched to the server's logs."""
    rid = (request.headers.get("x-request-id") or uuid.uuid4().hex)[:64]
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response

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
    model: str | None = Field(
        None, description="Model that wrote the answer (None if no generation ran)."
    )
    fallback_used: bool = Field(
        False,
        description=(
            "True when the main model was unavailable (overloaded, rate-limited or "
            "out of quota) and the fallback model answered."
        ),
    )


# --- Endpoints --------------------------------------------------------------
@app.get("/")
def root() -> dict[str, Any]:
    """What this service is, for people who open the base URL in a browser
    (the Streamlit app links to it). Never calls the LLM."""
    return {
        "service": "Insurance-Policy-RAG API",
        "description": "Grounded, page-cited answers about a sample insurance policy.",
        "endpoints": {"health": "GET /health", "ask": "POST /ask (bearer token)",
                      "stats": "GET /stats?days=7 (bearer token)", "docs": "/docs"},
        "source": "https://github.com/arashshams/Insurance-Policy-RAG",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    """Lightweight readiness probe; never calls the LLM."""
    return {
        "status": "ok",
        "index_present": os.path.isdir(DEMO_INDEX_DIR),
        "index_loaded": _collection is not None,
        "api_key_present": _api_key_present(),
        "auth_required": bool(_api_token()),
        "model_default": GEN_MODEL,
        "model_fallback": GEN_FALLBACK_MODEL or None,
        "metrics": monitoring.BACKEND,
    }


@app.get("/stats")
def stats(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="How many days back to aggregate."),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    """Aggregated monitoring numbers for the last `days` days (PLAN.md M5):
    request and error counts, "I don't know" rate by layer, fallback rate,
    latency, closest-passage distance, per day. Totals only, never individual
    questions. Same bearer token as /ask. Never calls the LLM."""
    _check_auth(authorization)
    _check_rate(request.client.host if request.client else "unknown")
    store = monitoring.get_store()
    if store is None:
        raise HTTPException(status_code=404, detail="Monitoring is turned off on this server.")
    now = time.time()
    monitoring.prune_old(store, now=now)
    try:
        events = store.events_since(now - days * 86400)
    except Exception as exc:  # noqa: BLE001 - report the store being down clearly
        log.warning("metrics read failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Monitoring data is unavailable "
                                                    "right now.") from exc
    summary = monitoring.summarize(events, days, now=now, threshold=DISTANCE_THRESHOLD)
    summary.update(backend=monitoring.BACKEND, version=APP_VERSION)
    return summary


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

    rid = getattr(request.state, "request_id", "-")
    started = time.monotonic()

    def _log_failure(status: int, exc: Exception) -> None:
        _record_request(rid=rid, status=status, seconds=time.monotonic() - started,
                        error=exc)

    try:
        result = answer_question_detailed(collection, req.question, k=req.k,
                                          fallback_model=GEN_FALLBACK_MODEL or None)
    except GeminiQuotaExhaustedError as exc:
        # Daily quota used up: tell the client when it resets, not "in a minute".
        _log_failure(503, exc)
        wait = int(exc.retry_after_s) + 1 if exc.retry_after_s else 3600
        raise HTTPException(
            status_code=503, detail=str(exc), headers={"Retry-After": str(wait)}
        ) from exc
    except GeminiUnavailableError as exc:
        # Gemini overloaded / rate-limited / not responding even after the
        # pipeline's retries: a temporary condition, so come back later.
        _log_failure(503, exc)
        raise HTTPException(
            status_code=503, detail=str(exc), headers={"Retry-After": "60"}
        ) from exc
    except Exception as exc:  # noqa: BLE001 - surface pipeline errors as 502
        _log_failure(502, exc)
        raise HTTPException(status_code=502, detail=f"Pipeline error: {exc}") from exc

    _record_request(rid=rid, status=200, seconds=time.monotonic() - started, result=result)

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
        model=result.get("model_used"),
        fallback_used=bool(result.get("fallback_used")),
    )
