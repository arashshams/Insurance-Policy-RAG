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

Run locally:
    uvicorn api.main:app --reload
    # then: curl -X POST localhost:8000/ask -H 'content-type: application/json' \
    #             -d '{"question": "Is physiotherapy covered?"}'
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# --- Make src/ importable whether run from repo root or api/ ----------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.rag_pipeline import (  # noqa: E402 - after sys.path setup
    IDK_ANSWER,
    K_DEFAULT,
    answer_question,
    load_persistent_collection,
)

# Path to the pre-built demo index shipped with the app (same as Streamlit).
DEMO_INDEX_DIR = os.environ.get(
    "DEMO_INDEX_DIR", str(REPO_ROOT / "app" / "demo_index")
)

app = FastAPI(
    title="Insurance-Policy-RAG API",
    version="1.0.0",
    description="Grounded, page-cited Q&A over an insurance policy.",
)

# Module-level cache for the opened collection (loaded lazily, once).
_collection = None


def _api_key_present() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


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
    question: str = Field(..., min_length=1, description="Natural-language question.")
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
    retrieved: list[RetrievedChunk]


# --- Endpoints --------------------------------------------------------------
@app.get("/health")
def health() -> dict[str, Any]:
    """Lightweight readiness probe; never calls the LLM."""
    return {
        "status": "ok",
        "index_present": os.path.isdir(DEMO_INDEX_DIR),
        "api_key_present": _api_key_present(),
        "model_default": os.environ.get("INSURANCE_RAG_GEN_MODEL", "gemini-flash-latest"),
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """Answer a question grounded in the bundled policy, cited by page."""
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
        answer, pages, retrieved = answer_question(collection, req.question, k=req.k)
    except Exception as exc:  # noqa: BLE001 - surface pipeline errors as 502
        raise HTTPException(status_code=502, detail=f"Pipeline error: {exc}") from exc

    abstained = (not retrieved) or answer.strip().lower().startswith(
        IDK_ANSWER.lower()
    )

    chunks = [
        RetrievedChunk(
            id=r.get("id", ""),
            page=r.get("metadata", {}).get("page"),
            score=r.get("score"),
            text=r.get("text", ""),
        )
        for r in retrieved
    ]

    return AskResponse(
        answer=answer,
        pages=[p for p in pages if p is not None],
        abstained=abstained,
        retrieved=chunks,
    )
