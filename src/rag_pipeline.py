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


def extract_pages(source):
    """Read a PDF and return a list of {"page": int, "text": str}.

    ``source`` may be a filesystem path (str/os.PathLike) OR a file-like /
    bytes object (as delivered by an upload widget). This keeps the same code
    path for dev (path on Drive) and the shipped app (uploaded bytes).
    """
    from pypdf import PdfReader

    reader = PdfReader(source)
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


def _get_chroma_client(persist_dir):
    """Return a Chroma client: Persistent when a dir is given, else Ephemeral."""
    import chromadb

    if persist_dir:
        os.makedirs(persist_dir, exist_ok=True)
        return chromadb.PersistentClient(path=persist_dir)
    return chromadb.EphemeralClient()


def build_index_from_pdf(source, persist_dir=None,
                         collection_name=COLLECTION_NAME,
                         source_name="policy.pdf"):
    """Build a Chroma collection from a PDF and return (collection, chunks).

    persist_dir=None  -> in-memory (shipped-app path, nothing persisted)
    persist_dir=<str> -> on-disk PersistentClient (dev path)

    The collection is deleted+recreated for a clean, reproducible rebuild.
    Embeddings are produced by embed_texts() (Section 2), so the vector space
    matches retrieval exactly and the 0.37 threshold stays valid.
    """
    pages = extract_pages(source)
    chunks = chunk_pages(pages, source_name=source_name)
    if not chunks:
        raise RuntimeError("No usable text extracted from the PDF.")

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

    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_collection(collection_name)


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
You are an assistant that answers employee insurance policy questions using only the provided context.
Context will be provided between <Context> and </Context>.
If the answer is not contained in the context, respond exactly with: \"I don't know\".
Do not hallucinate. Provide concise, policy-grounded answers.
"""

RAG_USER_TEMPLATE = """
<Context>
{context}
</Context>

<Question>
{question}
</Question>
"""


def retrieve_top_k(collection, query, k=K_DEFAULT, threshold=DISTANCE_THRESHOLD):
    """Return the k nearest chunks whose cosine distance <= threshold.

    Results above the threshold are dropped, so an off-topic query returns an
    empty list instead of forcing in irrelevant chunks. Each hit is a dict:
    {"id", "text", "metadata", "score"}.
    """
    q_emb = embed_query(query)
    results = collection.query(
        query_embeddings=[q_emb],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )
    ids = results["ids"][0]
    docs_text = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results.get("distances", [[]])[0]

    hits = []
    for idx, (_id, t, m) in enumerate(zip(ids, docs_text, metadatas)):
        score = float(distances[idx]) if distances else None
        # keep only sufficiently-similar chunks (None score => keep, can't judge)
        if score is None or score <= threshold:
            hits.append({"id": _id, "text": t, "metadata": m, "score": score})
    return hits


def answer_question(collection, question, k=K_DEFAULT, model_name=GEN_MODEL):
    """Retrieve grounded context and generate an answer.

    Returns (answer_text, pages, retrieved). If nothing passes the relevance
    threshold, short-circuits to IDK_ANSWER without calling the LLM.
    """
    # 1) Retrieve top-k relevant chunks (already distance-filtered)
    retrieved = retrieve_top_k(collection, question, k=k)

    # 1a) Short-circuit: no grounded context -> answer "I don't know".
    if not retrieved:
        return IDK_ANSWER, [], []

    # 2) Build context string (id header per chunk for citation)
    context_items = []
    for r in retrieved:
        header = f"[{r['id']}]"
        context_items.append(header + " " + r["text"])
    context_str = "\n\n---\n\n".join(context_items)

    # 3) Build messages and call chat completion (with retry/backoff)
    prompt_messages = [
        {"role": "system", "content": RAG_SYSTEM_MESSAGE},
        {"role": "user", "content": RAG_USER_TEMPLATE.format(
            context=context_str, question=question)},
    ]

    client = get_client()
    extra_body = {"reasoning_effort": GEN_REASONING_EFFORT} if GEN_REASONING_EFFORT else None

    def _generate(max_tokens):
        """One generation attempt, with the existing rate-limit retry/backoff."""
        retries = 0
        sleep_time = QUERY_INITIAL_SLEEP
        while True:
            try:
                kwargs = dict(
                    model=model_name,
                    messages=prompt_messages,
                    temperature=0.0,
                    max_tokens=max_tokens,
                )
                if extra_body:
                    kwargs["extra_body"] = extra_body
                return client.chat.completions.create(**kwargs)
            except RateLimitError:
                retries += 1
                if retries > QUERY_MAX_RETRIES:
                    raise RuntimeError(
                        f"Generation rate limit persists after {QUERY_MAX_RETRIES} "
                        f"retries."
                    )
                time.sleep(sleep_time)
                sleep_time *= 2

    response = _generate(GEN_MAX_TOKENS)
    finish_reason = getattr(response.choices[0], "finish_reason", None)

    # A response can still get cut off mid-sentence if the model "thinks"
    # through most of the budget before writing the visible answer. One retry
    # with double the budget recovers the common case instead of the app
    # silently shipping a truncated answer.
    if finish_reason in ("length", "MAX_TOKENS") and GEN_MAX_TOKENS < 4096:
        response = _generate(GEN_MAX_TOKENS * 2)
        finish_reason = getattr(response.choices[0], "finish_reason", None)

    answer_text = response.choices[0].message.content.strip()

    if finish_reason in ("length", "MAX_TOKENS"):
        answer_text += (
            "\n\n*(This answer may have been cut off before it finished — "
            "try asking again or narrowing the question.)*"
        )

    # 4) Extract page numbers for citation
    pages = sorted({
        doc.get("metadata", {}).get("page")
        for doc in retrieved
        if isinstance(doc, dict) and "page" in doc.get("metadata", {})
    })

    return answer_text, pages, retrieved
