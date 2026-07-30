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
