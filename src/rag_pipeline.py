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
# First calibrated 2026-07-27 on the original 8 + 4 questions, where 0.37
# separated in-scope (~0.25-0.34) from out-of-scope (~0.40-0.50). The larger
# question sets since then OVERLAP (near-miss out-of-scope questions come as
# close as 0.335; real ones reach 0.344), so no threshold alone separates them.
# 0.37 is kept (PLAN.md decision D1): it keeps every real question, and the
# model's refusal ("I don't know" from the prompt) stops the near-misses.
# IMPORTANT: this value is calibrated on the bundled SAMPLE policy only. It is
# not known to transfer to other documents; re-calibrate with
# `python -m src.evaluate --pdf your_policy.pdf --questions your_questions.json`
# (prints a suggested threshold) before relying on abstentions elsewhere.
DISTANCE_THRESHOLD = float(os.environ.get("INSURANCE_RAG_THRESHOLD", "0.37"))

# Threshold used for user-uploaded policies (uncalibrated documents). Defaults
# to the demo value; override separately once you have calibrated your own.
UPLOAD_DISTANCE_THRESHOLD = float(
    os.environ.get("INSURANCE_RAG_UPLOAD_THRESHOLD", str(DISTANCE_THRESHOLD))
)

# --- Upload guardrails (cost control for the shared, public app) -------------
# Hard caps on what an uploaded PDF may cost to embed.
MAX_UPLOAD_MB = float(os.environ.get("INSURANCE_RAG_MAX_UPLOAD_MB", "10"))
MAX_UPLOAD_PAGES = int(os.environ.get("INSURANCE_RAG_MAX_UPLOAD_PAGES", "60"))
MAX_UPLOAD_CHUNKS = int(os.environ.get("INSURANCE_RAG_MAX_UPLOAD_CHUNKS", "150"))

# Output-token budget for generation. On Gemini's OpenAI-compatible endpoint,
# internal "thinking" tokens are drawn from this same budget (not billed
# separately), so a low cap can silently truncate an answer before it's
# written. Kept generous here; GEN_REASONING_EFFORT below additionally turns
# thinking off outright on models that support it (harmless no-op otherwise).
GEN_MAX_TOKENS = int(os.environ.get("INSURANCE_RAG_MAX_TOKENS", "1024"))
GEN_REASONING_EFFORT = os.environ.get("INSURANCE_RAG_REASONING_EFFORT", "none")

# --- Chunking parameters (calibrated; MUST match notebook to keep 0.37 valid) ---
CHUNK_SIZE = int(os.environ.get("INSURANCE_RAG_CHUNK_SIZE", "800"))
CHUNK_OVERLAP = int(os.environ.get("INSURANCE_RAG_CHUNK_OVERLAP", "128"))
ENCODING_NAME = os.environ.get("INSURANCE_RAG_ENCODING", "cl100k_base")

# Page-quality gate: skip a page if its 'scramble ratio' exceeds this.
SCRAMBLE_THRESHOLD = float(os.environ.get("INSURANCE_RAG_SCRAMBLE_THRESHOLD", "0.5"))

# Retry/backoff for transient Gemini failures: free-tier rate limits (429),
# temporary overload / server errors (5xx, e.g. 503 "high demand") and
# connection errors or timeouts. Waits QUERY_INITIAL_SLEEP, then doubles.
QUERY_MAX_RETRIES = int(os.environ.get("INSURANCE_RAG_MAX_RETRIES", "5"))
QUERY_INITIAL_SLEEP = float(os.environ.get("INSURANCE_RAG_INITIAL_SLEEP", "2.0"))

# A 429 is NOT retried when Gemini says the quota resets later than this
# (seconds), or when it names a per-day quota: the free tier's daily request
# limit can't be waited out with backoff, so we fail fast instead.
LONG_QUOTA_RETRY_S = float(os.environ.get("INSURANCE_RAG_LONG_QUOTA_S", "300"))

# Per-request timeout (seconds) for Gemini calls, so a stalled connection
# fails and is retried instead of hanging for the client's 10-minute default.
REQUEST_TIMEOUT_S = float(os.environ.get("INSURANCE_RAG_REQUEST_TIMEOUT", "60"))

# Abstention answer returned when nothing relevant is retrieved
IDK_ANSWER = "I don't know"


def _normalize_answer(text: str) -> str:
    """Lower-case, unify apostrophes/quotes, drop citation tags, trailing
    punctuation and surrounding quotes, and collapse whitespace."""
    import re

    t = (text or "").replace("’", "'").replace("‘", "'")
    t = re.sub(r"[\[(]\s*doc_\d+(?:\s*,\s*doc_\d+)*\s*[\])]", " ", t)
    t = t.strip().strip("\"'`*_ ").rstrip(".!").strip("\"'`*_ ")
    return " ".join(t.lower().split())


def is_abstention(answer: str, idk: str = IDK_ANSWER) -> bool:
    """The ONE definition of "the system abstained", shared by the app, the API
    and the evaluation harness.

    True only when the whole answer is the IDK string (tolerant of case,
    curly apostrophes, quotes, trailing punctuation and stray citation tags).
    An answer that merely *starts* with "I don't know ..." and then goes on to
    say something is NOT an abstention: it contains content the user will read.
    """
    return _normalize_answer(answer) == _normalize_answer(idk)


# ----------------------------------------------------------------------------
# Gemini client factory + embedding functions
# ----------------------------------------------------------------------------

import time

from openai import OpenAI
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

# Errors worth retrying: they are about Gemini's state right now, not about
# the request. (APITimeoutError subclasses APIConnectionError; listed for
# clarity.) Auth / bad-request errors are NOT retried - they won't fix
# themselves.
_RETRYABLE_ERRORS = (RateLimitError, InternalServerError, APIConnectionError, APITimeoutError)


class GeminiUnavailableError(RuntimeError):
    """Gemini kept failing with transient errors after every retry."""


class GeminiQuotaExhaustedError(GeminiUnavailableError):
    """Gemini's quota is used up until a reset hours away (e.g. the free
    tier's daily request limit), so retrying now is pointless.

    `retry_after_s` is Gemini's suggested wait in seconds, if it gave one.
    Subclasses GeminiUnavailableError, so callers that handle that keep working.
    """

    def __init__(self, message: str, retry_after_s: float | None = None):
        super().__init__(message)
        self.retry_after_s = retry_after_s


def _quota_info(exc) -> tuple[bool, float | None]:
    """From a 429, return (long_window, retry_after_seconds).

    Gemini's error body names the exhausted quota (e.g.
    "GenerateRequestsPerDayPerProjectPerModel-FreeTier") and a retryDelay
    like "48341s". long_window is True for a per-day quota or a delay longer
    than LONG_QUOTA_RETRY_S. Parsed defensively: any format change just means
    "not recognised", which falls back to the normal retries.
    """
    import json
    import re

    try:
        blob = json.dumps(getattr(exc, "body", None), default=str)
    except Exception:
        blob = ""
    blob += " " + str(exc)
    m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s", blob)
    delay = float(m.group(1)) if m else None
    long_window = "PerDay" in blob or (delay is not None and delay > LONG_QUOTA_RETRY_S)
    return long_window, delay


def _humanize_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "after the quota resets (usually the next day)"
    if seconds >= 5400:
        return f"in about {round(seconds / 3600)} hours"
    if seconds >= 3600:
        return "in about an hour"
    return f"in about {max(1, round(seconds / 60))} minutes"


def _call_with_backoff(fn, what: str):
    """Call fn(), retrying transient Gemini errors with exponential backoff.

    Retries up to QUERY_MAX_RETRIES times, sleeping QUERY_INITIAL_SLEEP
    seconds before the first retry and doubling each time. Raises
    GeminiUnavailableError (chained to the last error) if it never succeeds.
    A 429 for a quota that resets hours later (daily limit) is not retried:
    it raises GeminiQuotaExhaustedError straight away.
    """
    retries = 0
    sleep_time = QUERY_INITIAL_SLEEP
    while True:
        try:
            return fn()
        except _RETRYABLE_ERRORS as exc:
            if isinstance(exc, RateLimitError):
                long_window, delay = _quota_info(exc)
                if long_window:
                    raise GeminiQuotaExhaustedError(
                        f"Gemini's request quota for {what} is used up "
                        "(the free tier allows a fixed number of requests per day). "
                        f"Please try again {_humanize_seconds(delay)}.",
                        retry_after_s=delay,
                    ) from exc
            retries += 1
            if retries > QUERY_MAX_RETRIES:
                kind = ("rate-limited" if isinstance(exc, RateLimitError)
                        else "temporarily unavailable")
                raise GeminiUnavailableError(
                    f"Gemini is {kind} ({what} failed after {QUERY_MAX_RETRIES} "
                    "retries). Please try again in a few minutes."
                ) from exc
            time.sleep(sleep_time)
            sleep_time *= 2


def _read_api_key() -> str:
    """Resolve the Gemini API key without storing or logging it.

    Resolution order (portable across app / local / Colab):
      1. GEMINI_API_KEY environment variable (used by the shipped app + local),
      2. Colab Secrets (userdata) as a fallback when running in Colab.
    google.colab is imported lazily so this module has no hard Colab dependency.
    """
    # GOOGLE_API_KEY is accepted as an alias because the app and API treat it
    # as a valid key; reading only GEMINI_API_KEY here made /health report
    # "key present" while every /ask failed.
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
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
        "No Gemini API key found. Set the GEMINI_API_KEY (or GOOGLE_API_KEY) environment variable "
        "(or add it to Colab Secrets when running in Colab)."
    )


def get_client() -> OpenAI:
    """Create an OpenAI-compatible client pointed at the Gemini endpoint.

    The client's own retries are off (max_retries=0): _call_with_backoff is
    the one retry policy. With both on, every attempt was retried again
    inside the client, which multiplied the waiting on a quota error.
    """
    return OpenAI(api_key=_read_api_key(), base_url=GEMINI_BASE_URL,
                  max_retries=0, timeout=REQUEST_TIMEOUT_S)


# Batch size for embedding many chunks at once (index build).
EMBED_BATCH = int(os.environ.get("INSURANCE_RAG_EMBED_BATCH", "16"))


def embed_query(text: str, client: OpenAI | None = None) -> list[float]:
    """Embed a single string, retrying transient errors with backoff."""
    client = client or get_client()
    resp = _call_with_backoff(
        lambda: client.embeddings.create(model=EMBED_MODEL, input=[text]),
        "embedding",
    )
    return resp.data[0].embedding


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
        resp = _call_with_backoff(
            lambda: client.embeddings.create(model=EMBED_MODEL, input=batch_texts),
            "embedding",
        )
        all_embeddings.extend([r.embedding for r in resp.data])
    return all_embeddings



# =============================================================================
# Section 3 - Index builder (dual-mode: dev-persistent / app-ephemeral)
# =============================================================================
# Dev mode  (persist_dir is a path): build a PersistentClient index on disk so
#            the 37-chunk index can be reloaded fast without re-embedding.
# App mode  (persist_dir is None):   embed the user-uploaded PDF straight into an
#            in-memory EphemeralClient; NOTHING is written to disk (privacy).
# chunks.json is DEV-ONLY and is never written by the app path.

import re as _re


def _scramble_ratio(text: str) -> float:
    """Fraction of 'word-like' tokens that look scrambled/garbage.

    Used as a page-quality gate to skip pages that pypdf extracted poorly
    (e.g. heavily-graphical or OCR-hostile pages). A page is dropped when the
    ratio exceeds SCRAMBLE_THRESHOLD.
    """
    tokens = _re.findall(r"[A-Za-z]+", text)
    if not tokens:
        return 1.0
    bad = 0
    for tok in tokens:
        # a token with no vowels and length >= 4 is almost certainly garbage
        if len(tok) >= 4 and not _re.search(r"[aeiouAEIOU]", tok):
            bad += 1
    return bad / len(tokens)


class DocumentTooLargeError(ValueError):
    """Raised when a PDF exceeds the configured page / chunk caps."""


def extract_pages(source, max_pages=None):
    """Read a PDF and return a list of {"page": int, "text": str}.

    ``source`` may be a filesystem path (str/os.PathLike) OR a file-like /
    bytes object (as delivered by an upload widget). This keeps the same code
    path for dev (path on Drive) and the shipped app (uploaded bytes).

    ``max_pages`` (optional) rejects longer documents BEFORE any text is
    extracted or embedded, so an oversized upload costs nothing.
    """
    from pypdf import PdfReader

    reader = PdfReader(source)
    if max_pages is not None and len(reader.pages) > max_pages:
        raise DocumentTooLargeError(
            f"This PDF has {len(reader.pages)} pages; the limit is {max_pages}."
        )
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({"page": i + 1, "text": text})
    return pages


def chunk_pages(pages, source_name="policy.pdf"):
    """Split per-page text into overlapping chunks (calibrated splitter).

    Returns a list of chunk dicts: {"id", "text", "page", "source"}.
    Splitting is done per page so page numbers stay accurate in metadata.
    Empty pages and low-quality (scrambled) pages are skipped.
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=ENCODING_NAME,
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    chunks = []
    idx = 0
    for pg in pages:
        text = (pg.get("text") or "").strip()
        if not text:
            continue
        if _scramble_ratio(text) > SCRAMBLE_THRESHOLD:
            continue
        for piece in splitter.split_text(text):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append({
                "id": f"doc_{idx}",
                "text": piece,
                "page": pg["page"],
                "source": source_name,
            })
            idx += 1
    return chunks


def _chroma_settings():
    """Shared Chroma settings. Anonymous telemetry is OFF: this project avoids
    sending anything about user documents/usage to third parties by default.
    (All clients in a process must use identical settings, hence one helper.)"""
    from chromadb.config import Settings

    return Settings(anonymized_telemetry=False)


def _get_chroma_client(persist_dir):
    """Return a Chroma client: Persistent when a dir is given, else Ephemeral.

    NOTE: every EphemeralClient in a process shares ONE in-memory store. On a
    multi-user host (e.g. Streamlit Community Cloud, one process for all
    visitors) that means collection names are global, so the app path must
    use a unique collection name per upload (see build_index_from_pdf).
    """
    import chromadb

    if persist_dir:
        os.makedirs(persist_dir, exist_ok=True)
        return chromadb.PersistentClient(path=persist_dir, settings=_chroma_settings())
    return chromadb.EphemeralClient(settings=_chroma_settings())


def build_index_from_pdf(source, persist_dir=None,
                         collection_name=None,
                         source_name="policy.pdf",
                         max_pages=None,
                         max_chunks=None):
    """Build a Chroma collection from a PDF and return (collection, chunks).

    persist_dir=None  -> in-memory (shipped-app path, nothing persisted)
    persist_dir=<str> -> on-disk PersistentClient (dev path)

    max_pages / max_chunks (optional) cap what one document may cost to embed;
    exceeding either raises DocumentTooLargeError before any embedding call.
    The app passes MAX_UPLOAD_PAGES / MAX_UPLOAD_CHUNKS; dev builds pass None.

    collection_name:
      * dev path: defaults to COLLECTION_NAME; the collection is
        deleted+recreated for a clean, reproducible rebuild.
      * app path: defaults to a fresh unique name per call. The in-memory
        store is shared by every session in the process, so a fixed name
        would let one user's upload delete another user's index.
    Embeddings are produced by embed_texts() (Section 2), so the vector space
    matches retrieval exactly and the 0.37 threshold stays valid.
    """
    if collection_name is None:
        if persist_dir:
            collection_name = COLLECTION_NAME
        else:
            import uuid

            collection_name = f"upload_{uuid.uuid4().hex}"

    pages = extract_pages(source, max_pages=max_pages)
    chunks = chunk_pages(pages, source_name=source_name)
    if not chunks:
        raise RuntimeError("No usable text extracted from the PDF.")
    if max_chunks is not None and len(chunks) > max_chunks:
        raise DocumentTooLargeError(
            f"This PDF splits into {len(chunks)} chunks; the limit is {max_chunks}."
        )

    client = _get_chroma_client(persist_dir)

    # clean rebuild: drop any stale collection first
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    collection = client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    texts = [c["text"] for c in chunks]
    embeddings = embed_texts(texts)
    collection.add(
        ids=[c["id"] for c in chunks],
        documents=texts,
        metadatas=[{"page": c["page"], "source": c["source"]} for c in chunks],
        embeddings=embeddings,
    )
    return collection, chunks


def load_persistent_collection(persist_dir=PERSIST_DIR,
                               collection_name=COLLECTION_NAME):
    """Dev fast-path: reopen an existing on-disk index without re-embedding."""
    import chromadb

    client = chromadb.PersistentClient(path=persist_dir, settings=_chroma_settings())
    return client.get_collection(collection_name)


def drop_collection(collection) -> None:
    """Free an app-path (in-memory) collection once it is no longer needed.

    Safe to call on an already-deleted collection. Used by the app when a
    session replaces its upload, so old documents don't linger in memory.
    """
    if collection is None:
        return
    import chromadb

    try:
        chromadb.EphemeralClient(settings=_chroma_settings()).delete_collection(
            collection.name
        )
    except Exception:
        pass


def save_chunks(chunks, path=CHUNKS_PATH):
    """Optional DEV-ONLY helper: dump chunks to JSON for reproducibility.

    Never called by the shipped in-memory app path.
    """
    import json

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    return path


# =============================================================================
# Section 4 - Retrieval + grounded generation
# =============================================================================
# retrieve_top_k(): embed the query, pull the k nearest chunks, drop any whose
#   cosine distance exceeds DISTANCE_THRESHOLD (0.37, calibrated) so off-topic
#   queries return [].
# answer_question(): if nothing passed the threshold, short-circuit to
#   IDK_ANSWER WITHOUT calling the LLM (drives out-of-scope abstention);
#   otherwise build a grounded prompt and generate.
# The collection is passed in explicitly so the same code serves both the
# dev-persistent and the app-ephemeral index.

RAG_SYSTEM_MESSAGE = """
You are an assistant that answers insurance policy questions using only the provided context.
Context will be provided between <Context> and </Context>. Each passage starts with its id in square brackets, e.g. [doc_12].
If the answer is not contained in the context, respond exactly with: \"I don't know\" and nothing else.
Do not hallucinate. Provide concise, policy-grounded answers.
After each sentence that uses the context, cite the id(s) of the passage(s) it came from in square brackets, e.g. [doc_12] or [doc_3, doc_7]. Cite only ids that appear in the context.
"""

RAG_USER_TEMPLATE = """
<Context>
{context}
</Context>

<Question>
{question}
</Question>
"""

# Matches one citation group: [doc_3], [doc_3, doc_7] or the (doc_3) variant
_CITATION_RE = _re.compile(r"[\[(]\s*(doc_\d+(?:\s*,\s*doc_\d+)*)\s*[\])]")


def extract_citations(answer: str, valid_ids) -> tuple[str, list[str]]:
    """Strip [doc_N] citation tags from an answer and return (clean_text, ids).

    Only ids that were actually in the retrieved context are returned (a model
    citing an id it was never shown is ignored). Order of first citation is
    preserved; duplicates are removed.
    """
    valid = set(valid_ids)
    cited: list[str] = []
    for group in _CITATION_RE.findall(answer or ""):
        for _id in _re.split(r"\s*,\s*", group.strip()):
            if _id in valid and _id not in cited:
                cited.append(_id)
    clean = _CITATION_RE.sub("", answer or "")
    clean = _re.sub(r"[ \t]+([.,;:!?])", r"\1", clean)   # "covered ." -> "covered."
    clean = _re.sub(r"[ \t]{2,}", " ", clean).strip()
    return clean, cited


def _query_chunks(collection, query, k=K_DEFAULT):
    """Embed the query and return the k nearest chunks, UNFILTERED, as
    {"id", "text", "metadata", "score"} dicts (score = cosine distance)."""
    q_emb = embed_query(query)
    results = collection.query(
        query_embeddings=[q_emb],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    ids = results["ids"][0]
    docs_text = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = (results.get("distances") or [[]])[0]

    hits = []
    for idx, (_id, t, m) in enumerate(zip(ids, docs_text, metadatas)):
        score = float(distances[idx]) if distances else None
        hits.append({"id": _id, "text": t, "metadata": m or {}, "score": score})
    return hits


def _apply_threshold(hits, threshold):
    # keep only sufficiently-similar chunks (None score => keep, can't judge)
    return [h for h in hits if h["score"] is None or h["score"] <= threshold]


def retrieve_top_k(collection, query, k=K_DEFAULT, threshold=DISTANCE_THRESHOLD):
    """Return the k nearest chunks whose cosine distance <= threshold.

    Results above the threshold are dropped, so an off-topic query returns an
    empty list instead of forcing in irrelevant chunks. Each hit is a dict:
    {"id", "text", "metadata", "score"}.
    """
    return _apply_threshold(_query_chunks(collection, query, k=k), threshold)


def _pages_of(chunks) -> list:
    return sorted({
        c.get("metadata", {}).get("page")
        for c in chunks
        if isinstance(c, dict) and c.get("metadata", {}).get("page") is not None
    })


def answer_question_detailed(collection, question, k=K_DEFAULT,
                             model_name=GEN_MODEL,
                             threshold=DISTANCE_THRESHOLD) -> dict:
    """Retrieve grounded context, generate an answer, and report how it was made.

    Returns a dict:
      answer              final answer text (citation tags stripped)
      pages               cited page numbers (see citations_verified)
      retrieved           chunks that passed the threshold
      abstained           is_abstention(answer) - the single shared definition
      cited_ids           chunk ids the model cited that were in its context
      citations_verified  True  -> `pages` are the pages of the cited chunks
                          False -> the model cited nothing usable, so `pages`
                                   falls back to every retrieved chunk's page
      nearest_distance    distance of the closest chunk BEFORE thresholding
                          (how close an abstained question came; for calibration)
      candidates          all k nearest chunks BEFORE thresholding, as
                          {"id", "page", "distance"} (no text). Lets the
                          evaluation measure recall before/after the threshold
                          and re-score other thresholds without new API calls.
      threshold           the threshold that was applied
      model_requested     model name sent to the API (may be an alias)
      model_resolved      model name the API reported back, if any (Gemini's
                          OpenAI-compatible endpoint echoes the requested name)
      finish_reason       generation finish reason, if generation ran
      generation_calls    generation requests made (0 if the threshold
                          short-circuited, 2 if a truncated answer was retried);
                          lets the evaluation budget the daily quota
    If nothing passes the threshold, short-circuits to IDK_ANSWER without
    calling the LLM.
    """
    all_hits = _query_chunks(collection, question, k=k)
    retrieved = _apply_threshold(all_hits, threshold)
    distances = [h["score"] for h in all_hits if h["score"] is not None]

    result = {
        "answer": IDK_ANSWER,
        "pages": [],
        "retrieved": retrieved,
        "abstained": True,
        "cited_ids": [],
        "citations_verified": False,
        "nearest_distance": min(distances) if distances else None,
        "candidates": [
            {"id": h["id"], "page": h["metadata"].get("page"), "distance": h["score"]}
            for h in all_hits
        ],
        "threshold": threshold,
        "model_requested": model_name,
        "model_resolved": None,
        "finish_reason": None,
        "generation_calls": 0,
    }

    # Short-circuit: no grounded context -> "I don't know" (no LLM call).
    if not retrieved:
        return result

    # Build context string (id header per chunk so the model can cite it)
    context_str = "\n\n---\n\n".join(f"[{r['id']}] {r['text']}" for r in retrieved)

    prompt_messages = [
        {"role": "system", "content": RAG_SYSTEM_MESSAGE},
        {"role": "user", "content": RAG_USER_TEMPLATE.format(
            context=context_str, question=question)},
    ]

    client = get_client()
    extra_body = {"reasoning_effort": GEN_REASONING_EFFORT} if GEN_REASONING_EFFORT else None

    def _generate(max_tokens):
        """One generation attempt, retrying transient errors with backoff."""
        kwargs = dict(
            model=model_name,
            messages=prompt_messages,
            temperature=0.0,
            max_tokens=max_tokens,
        )
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = _call_with_backoff(
            lambda: client.chat.completions.create(**kwargs), "generation"
        )
        result["generation_calls"] += 1
        return response

    response = _generate(GEN_MAX_TOKENS)
    finish_reason = getattr(response.choices[0], "finish_reason", None)

    # A response can still get cut off mid-sentence if the model "thinks"
    # through most of the budget before writing the visible answer. One retry
    # with double the budget recovers the common case instead of the app
    # silently shipping a truncated answer.
    if finish_reason in ("length", "MAX_TOKENS") and GEN_MAX_TOKENS < 4096:
        response = _generate(GEN_MAX_TOKENS * 2)
        finish_reason = getattr(response.choices[0], "finish_reason", None)

    result["finish_reason"] = finish_reason
    # Record the model name the API reports. Gemini's OpenAI-compatible
    # endpoint currently just echoes the requested name (alias included), so
    # this only identifies an exact version if one was requested.
    resolved = getattr(response, "model", None)
    result["model_resolved"] = resolved if isinstance(resolved, str) and resolved else None

    # content can be None (e.g. a safety block or an empty completion);
    # treat that as an abstention rather than crashing on .strip().
    content = response.choices[0].message.content
    if not content or not content.strip():
        return result

    answer_text, cited_ids = extract_citations(
        content.strip(), [r["id"] for r in retrieved]
    )

    if is_abstention(answer_text) or not answer_text:
        # The model itself declined: no answer, so nothing to cite.
        return result

    if finish_reason in ("length", "MAX_TOKENS"):
        answer_text += (
            "\n\n*(This answer may have been cut off before it finished — "
            "try asking again or narrowing the question.)*"
        )

    if cited_ids:
        cited_chunks = [r for r in retrieved if r["id"] in set(cited_ids)]
        pages = _pages_of(cited_chunks)
        verified = True
    else:
        pages = _pages_of(retrieved)
        verified = False

    result.update(
        answer=answer_text,
        pages=pages,
        abstained=False,
        cited_ids=cited_ids,
        citations_verified=verified,
    )
    return result


def answer_question(collection, question, k=K_DEFAULT, model_name=GEN_MODEL,
                    threshold=DISTANCE_THRESHOLD):
    """Retrieve grounded context and generate an answer.

    Returns (answer_text, pages, retrieved). `pages` are the pages of the
    chunks the model cited (falling back to all retrieved pages if it cited
    none); `pages` is [] whenever the system abstains. Use
    answer_question_detailed() for abstention / citation / distance metadata.
    """
    r = answer_question_detailed(
        collection, question, k=k, model_name=model_name, threshold=threshold
    )
    return r["answer"], r["pages"], r["retrieved"]
