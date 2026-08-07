"""
Streamlit MVP for Insurance-Policy-RAG.

Thin UI layer over src/rag_pipeline.py. Two modes:
- Bundled-policy demo: loads a pre-built, on-disk Chroma index shipped
  with the app (no embedding calls at startup -> free-tier friendly).
- User upload: builds a per-session, in-memory ephemeral index from an
  uploaded PDF and persists nothing (privacy).

Demo mode can optionally be served by the FastAPI backend (api/main.py):
set INSURANCE_RAG_API_URL to the backend's base URL and demo questions are
answered over HTTP instead of in-process. Upload mode always runs in-process
(the API only serves the bundled demo policy). If the variable is unset the
app behaves exactly as before.

Run locally: streamlit run app/streamlit_app.py
"""

import io
import os
import sys
from pathlib import Path

import streamlit as st

# --- Make src/ importable whether run from repo root or app/ ---------------
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# --- Page config (MUST be the first Streamlit command in the script) --------
st.set_page_config(
    page_title="Insurance-Policy-RAG",
    page_icon="\U0001F4C4",
    layout="centered",
)

# --- Secrets / config -------------------------------------------------------
# On Streamlit Community Cloud, put GEMINI_API_KEY (and optionally
# INSURANCE_RAG_ROOT) in the app's Secrets. Mirror them into the environment
# so rag_pipeline's env-based config picks them up unchanged.
#
# We only touch st.secrets when a secrets.toml actually exists. Merely reading
# st.secrets with no file present makes Streamlit log "No secrets files found"
# (not a catchable exception), so a local run with just an env var would spam
# that message. Guarding on the file keeps local runs clean while still using
# secrets on Streamlit Community Cloud.
def _secrets_file_exists() -> bool:
    candidates = [
        Path.home() / ".streamlit" / "secrets.toml",
        REPO_ROOT / ".streamlit" / "secrets.toml",
    ]
    return any(p.is_file() for p in candidates)

def _load_secrets_into_env() -> None:
    if not _secrets_file_exists():
        return
    for key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "INSURANCE_RAG_ROOT",
                "INSURANCE_RAG_API_URL"):
        try:
            value = st.secrets.get(key)
        except Exception:
            value = None
        if value is not None and key not in os.environ:
            os.environ[key] = str(value)

_load_secrets_into_env()

def _api_key_present() -> bool:
    """True if a Gemini/Google API key is available for generation."""
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

# Optional FastAPI backend base URL. When set, demo mode calls it over HTTP
# instead of running the pipeline in-process. Trailing slash is trimmed so we
# can safely append "/ask".
API_URL = os.environ.get("INSURANCE_RAG_API_URL", "").strip().rstrip("/")

# Path to the pre-built demo index shipped with the app (Option B).
# Overridable via secrets/env if you store it elsewhere.
DEMO_INDEX_DIR = os.environ.get(
    "DEMO_INDEX_DIR", str(REPO_ROOT / "app" / "demo_index")
)

# Example questions surfaced as one-click buttons in demo mode.
EXAMPLE_QUESTIONS = [
    "Is physiotherapy covered?",
    "Are pre-authorizations required?",
    "What expenses are excluded?",
]

from src.rag_pipeline import (
    answer_question,
    build_index_from_pdf,
    load_persistent_collection,
)

st.title("Insurance-Policy-RAG")
st.caption(
    "Ask natural-language questions about an insurance policy. Answers are "
    "grounded in the document, cited by page, and abstain when the policy "
    "doesn't cover the question."
)

with st.expander("How it works"):
    st.markdown(
        "1. Your question is embedded and matched against the policy's "
        "indexed passages (semantic retrieval).\n"
        "2. Only passages above a similarity threshold are kept, so "
        "off-topic questions retrieve nothing.\n"
        "3. The answer is generated **strictly from those passages** and "
        "each claim is cited by page.\n"
        "4. If nothing relevant is retrieved, the system says "
        "*\"I don't know\"* rather than guessing."
    )

# --- Sidebar: mode selection ------------------------------------------------
with st.sidebar:
    st.header("Mode")
    mode = st.radio(
        "Choose how to run:",
        options=("Bundled-policy demo", "Upload my own policy"),
        index=0,
        help=(
            "Demo loads a pre-built index of a published SAMPLE policy. "
            "Upload builds a private, per-session index from your PDF that "
            "is never stored."
        ),
    )
    st.divider()
    if API_URL:
        st.caption(f"Demo served by API: {API_URL}")
    elif _api_key_present():
        st.caption("API key detected.")
    else:
        st.caption("No GEMINI_API_KEY set - answers will be unavailable.")
    st.caption(
        "Runs on the Gemini free tier. Not legal or financial advice."
    )

@st.cache_resource(show_spinner=False)
def _load_demo_collection(index_dir: str):
    """Load the pre-built persistent Chroma index for the demo (cached).

    Cached across reruns so the on-disk index is opened once per session,
    with no embedding calls at startup (free-tier friendly).
    """
    return load_persistent_collection(persist_dir=index_dir)

@st.cache_resource(show_spinner=False)
def _build_uploaded_collection(file_bytes: bytes, cache_key: str):
    """Build an in-memory ephemeral index from uploaded PDF bytes (cached).

    persist_dir is None, so rag_pipeline uses an EphemeralClient and writes
    NOTHING to disk. Cached on (name, size) so we embed once per uploaded
    file per session instead of on every rerun (saves free-tier quota).
    The returned tuple's chunks are unused here but kept for parity.
    """
    collection, _chunks = build_index_from_pdf(
        io.BytesIO(file_bytes), persist_dir=None, source_name=cache_key
    )
    return collection

def _answer_via_api(question: str):
    """Ask the FastAPI backend and normalize its reply to the in-process shape.

    Returns (answer, pages, retrieved) so the rest of the UI is identical
    whether the answer came from the API or from the local pipeline. Raises
    on transport/HTTP errors so the caller can surface them.
    """
    import requests

    resp = requests.post(
        f"{API_URL}/ask", json={"question": question}, timeout=60
    )
    resp.raise_for_status()
    data = resp.json()
    retrieved = [
        {
            "id": c.get("id", ""),
            "text": c.get("text", ""),
            "metadata": {"page": c.get("page")},
            "score": c.get("score"),
        }
        for c in data.get("retrieved", [])
    ]
    return data.get("answer", ""), data.get("pages", []), retrieved

def _render_answer(question: str, collection, use_api: bool = False) -> None:
    """Run one question and render the grounded result.

    When use_api is True the FastAPI backend answers over HTTP (the API key
    lives on the server); otherwise the local pipeline runs in-process and a
    local key is required.
    """
    if not use_api and not _api_key_present():
        st.error(
            "No GEMINI_API_KEY is set, so the system cannot generate an "
            "answer. Set it as an environment variable locally, or in the "
            "app's Secrets on Streamlit Community Cloud, then rerun."
        )
        return

    try:
        with st.spinner("Retrieving and generating a grounded answer..."):
            if use_api:
                answer, pages, retrieved = _answer_via_api(question)
            else:
                answer, pages, retrieved = answer_question(collection, question)
    except Exception as exc:  # noqa: BLE001 - surface API/pipeline errors
        st.error(f"Could not get an answer: {exc}")
        return

    if answer.strip().lower().startswith("i don't know"):
        st.warning(
            "**I don't know.** The passages retrieved from the policy don't "
            "cover this question, so the system abstains rather than guess. "
            "Try rephrasing, or ask about something the policy addresses."
        )
        return

    st.markdown("### Answer")
    st.write(answer)
    if pages:
        cited = ", ".join(str(p) for p in pages)
        st.caption(f"Cited page(s): {cited}")

    with st.expander(f"Retrieved passages ({len(retrieved)})"):
        for r in retrieved:
            page = r.get("metadata", {}).get("page", "?")
            score = r.get("score")
            score_str = f"{score:.3f}" if isinstance(score, float) else "n/a"
            st.markdown(f"**Page {page}** - distance {score_str}")
            st.write(r.get("text", ""))
            st.divider()

def _query_ui(collection, key_prefix: str, show_examples: bool = True,
              use_api: bool = False) -> None:
    """Shared question UI (example buttons + free-text) used by both modes."""
    clicked = None
    if show_examples:
        st.write("Try an example question:")
        cols = st.columns(len(EXAMPLE_QUESTIONS))
        for col, q in zip(cols, EXAMPLE_QUESTIONS):
            if col.button(q, use_container_width=True, key=f"{key_prefix}_{q}"):
                clicked = q

    typed = st.text_input(
        "...or ask your own question:", key=f"{key_prefix}_query"
    )
    if st.button("Ask", type="primary", key=f"{key_prefix}_ask"):
        clicked = typed.strip() or clicked
        if not clicked:
            st.info("Type a question above (or pick an example) first.")

    if clicked:
        _render_answer(clicked, collection, use_api=use_api)

def render_demo_mode() -> None:
    """Bundled-policy demo: query the pre-built SAMPLE-policy index.

    If INSURANCE_RAG_API_URL is set, questions are answered by the FastAPI
    backend over HTTP and no local index/key is needed. Otherwise the on-disk
    demo index is opened and queried in-process.
    """
    st.info(
        "Demo mode uses a pre-built index of a published, SAMPLE-watermarked "
        "policy (Manulife FlexCare). It is a stand-in for development only."
    )

    if API_URL:
        _query_ui(None, key_prefix="demo", show_examples=True, use_api=True)
        return

    if not os.path.isdir(DEMO_INDEX_DIR):
        st.error(
            "Demo index not found. Build it once and commit it to "
            f"'{os.path.relpath(DEMO_INDEX_DIR, REPO_ROOT)}' (see app/README)."
        )
        return

    try:
        collection = _load_demo_collection(DEMO_INDEX_DIR)
    except Exception as exc:  # noqa: BLE001 - surface load errors to the user
        st.error(f"Could not open the demo index: {exc}")
        return

    _query_ui(collection, key_prefix="demo", show_examples=True)

def render_upload_mode() -> None:
    """User-upload: build a per-session, in-memory index from a PDF."""
    st.info(
        "Upload a policy PDF to ask questions about it. The index is built "
        "in memory for this session only and is never stored."
    )

    uploaded = st.file_uploader("Policy PDF", type=["pdf"])
    if uploaded is None:
        st.caption("Waiting for a PDF...")
        return

    cache_key = f"{uploaded.name}:{uploaded.size}"
    try:
        with st.spinner("Embedding your policy (one-time per upload)..."):
            collection = _build_uploaded_collection(
                uploaded.getvalue(), cache_key
            )
    except Exception as exc:  # noqa: BLE001 - surface build errors to the user
        st.error(f"Could not process this PDF: {exc}")
        return

    st.success(f"Indexed '{uploaded.name}'. Ask a question below.")
    _query_ui(collection, key_prefix="upload", show_examples=False)

# --- Mode routing -----------------------------------------------------------
if mode == "Bundled-policy demo":
    render_demo_mode()
else:
    render_upload_mode()
