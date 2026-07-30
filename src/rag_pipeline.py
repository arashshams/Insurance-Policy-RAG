"""
rag_pipeline.py — Insurance Policy RAG pipeline (shared module).

Consolidates the retrieval + grounded-generation logic previously spread
across notebooks 01-03 into one importable module. All configuration lives
in the Config section below; every value can be overridden via environment
variables so the same code runs unchanged in Colab, locally, and in the app.

Two runtime modes are supported by design:
  * DEV / calibration  -> persistent on-disk Chroma index + chunks.json
                          artifact (avoids re-embedding the fixed SAMPLE
                          policy on every run; saves free-tier quota).
  * SHIPPED APP         -> user uploads a policy per session; we embed straight
                          from the uploaded bytes into an in-memory (ephemeral)
                          Chroma collection and persist NOTHING to disk.
The dev-only paths below (CHUNKS_PATH, PERSIST_DIR) are convenient defaults,
NOT hard requirements: the index-builder decides whether to persist.
"""

from __future__ import annotations

import os

# ----------------------------------------------------------------------------
# Configuration (single source of truth; env-var overridable)
# ----------------------------------------------------------------------------

# Project root. Defaults to the Google Drive location used during development;
# override with INSURANCE_RAG_ROOT so local runs / the app can point elsewhere.
# NOTE: the shipped app does not rely on this path at all - it works purely
# from the uploaded file in memory.
PROJECT_ROOT = os.environ.get(
    "INSURANCE_RAG_ROOT",
    "/content/drive/MyDrive/Insurance-Policy-RAG",
)

# --- Dev-only convenience paths (ignored in the app's in-memory mode) --------
ARTIFACTS_DIR = os.environ.get(
    "INSURANCE_RAG_ARTIFACTS", os.path.join(PROJECT_ROOT, "artifacts")
)
CHUNKS_PATH = os.path.join(ARTIFACTS_DIR, "chunks.json")  # dev reproducibility
PERSIST_DIR = os.environ.get(
    "INSURANCE_RAG_CHROMA", os.path.join(PROJECT_ROOT, "chroma")
)

# Chroma collection name (must match the persistent index built by NB02)
COLLECTION_NAME = os.environ.get("INSURANCE_RAG_COLLECTION", "insurance_policy_cvdb")

# --- Models (Gemini via the OpenAI-compatible endpoint) ----------------------
EMBED_MODEL = os.environ.get("INSURANCE_RAG_EMBED_MODEL", "gemini-embedding-001")
GEN_MODEL = os.environ.get("INSURANCE_RAG_GEN_MODEL", "gemini-flash-latest")
GEMINI_BASE_URL = os.environ.get(
    "INSURANCE_RAG_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
)

# --- Retrieval / generation parameters ---------------------------------------
K_DEFAULT = int(os.environ.get("INSURANCE_RAG_K", "4"))

# Chunks whose distance exceeds this are treated as irrelevant (abstain).
# Calibrated 2026-07-27 against the eval set (37-chunk index): in-scope
# distances ~0.25-0.34, out-of-scope ~0.40-0.50; 0.37 cleanly separates them.
DISTANCE_THRESHOLD = float(os.environ.get("INSURANCE_RAG_THRESHOLD", "0.37"))

# Query-time retry/backoff for free-tier rate limits (mirrors indexing loop)
QUERY_MAX_RETRIES = int(os.environ.get("INSURANCE_RAG_MAX_RETRIES", "5"))
QUERY_INITIAL_SLEEP = float(os.environ.get("INSURANCE_RAG_INITIAL_SLEEP", "2.0"))

# Abstention answer returned when nothing relevant is retrieved
IDK_ANSWER = "I don't know"


# ----------------------------------------------------------------------------
# Gemini client factory + embedding functions
# ----------------------------------------------------------------------------

import time

from openai import OpenAI
from openai import RateLimitError


def _read_api_key() -> str:
    """Resolve the Gemini API key without storing or logging it.

    Resolution order (portable across app / local / Colab):
      1. GEMINI_API_KEY environment variable (used by the shipped app + local),
      2. Colab Secrets (userdata) as a fallback when running in Colab.
    google.colab is imported lazily so this module has no hard Colab dependency.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        return key
    try:
        from google.colab import userdata  # lazy: only exists in Colab
        key = userdata.get("GEMINI_API_KEY")
        if key:
            return key
    except Exception:
        pass
    raise RuntimeError(
        "No Gemini API key found. Set the GEMINI_API_KEY environment variable "
        "(or add it to Colab Secrets when running in Colab)."
    )


def get_client() -> OpenAI:
    """Create an OpenAI-compatible client pointed at the Gemini endpoint."""
    return OpenAI(api_key=_read_api_key(), base_url=GEMINI_BASE_URL)


# Batch size for embedding many chunks at once (index build).
EMBED_BATCH = int(os.environ.get("INSURANCE_RAG_EMBED_BATCH", "16"))


def embed_query(text: str, client: OpenAI | None = None) -> list[float]:
    """Embed a single string, retrying with exponential backoff on rate limits."""
    client = client or get_client()
    retries = 0
    sleep_time = QUERY_INITIAL_SLEEP
    while True:
        try:
            resp = client.embeddings.create(model=EMBED_MODEL, input=[text])
            return resp.data[0].embedding
        except RateLimitError:
            retries += 1
            if retries > QUERY_MAX_RETRIES:
                raise RuntimeError(
                    f"Embedding rate limit persists after {QUERY_MAX_RETRIES} retries."
                )
            time.sleep(sleep_time)
            sleep_time *= 2


def embed_texts(
    texts: list[str],
    client: OpenAI | None = None,
    batch: int = EMBED_BATCH,
    progress: bool = False,
) -> list[list[float]]:
    """Embed many strings in batches, with the same retry/backoff pacing.

    Used when building an index (dev-persistent or app-ephemeral). `progress`
    optionally shows a tqdm bar; kept off by default so the app stays quiet.
    """
    client = client or get_client()

    iterator = range(0, len(texts), batch)
    if progress:
        from tqdm import tqdm
        iterator = tqdm(iterator, desc="Embedding batches")

    all_embeddings: list[list[float]] = []
    for i in iterator:
        batch_texts = texts[i : i + batch]
        retries = 0
        sleep_time = QUERY_INITIAL_SLEEP
        while True:
            try:
                resp = client.embeddings.create(model=EMBED_MODEL, input=batch_texts)
                all_embeddings.extend([r.embedding for r in resp.data])
                break
            except RateLimitError:
                retries += 1
                if retries > QUERY_MAX_RETRIES:
                    raise RuntimeError(
                        f"Embedding rate limit persists after {QUERY_MAX_RETRIES} "
                        f"retries. Consider waiting longer or reducing batch size."
                    )
                time.sleep(sleep_time)
                sleep_time *= 2
    return all_embeddings
