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

# Example questions surfaced as one-click buttons in demo mode. Kept close to
# the eval-calibrated wording (notebooks/eval/eval_questions.json) and the
# policy's own terms - e.g. "prior authorization", not "pre-authorization"
# (a phrase that doesn't appear in the document) - so every example button
# reliably clears the retrieval threshold instead of abstaining.
EXAMPLE_QUESTIONS = [
    "Is physiotherapy covered?",
    "Is prior authorization required?",
    "What expenses are excluded?",
]

from src.rag_pipeline import (
    answer_question,
    build_index_from_pdf,
    load_persistent_collection,
)

st.title("Insurance-Policy-RAG")
st.caption(
    "Ask questions about an insurance policy in plain English and get "
    "answers straight from the document — with the page number to back "
    "it up. If the policy doesn't say, you'll get an honest \"I don't "
    "know\" instead of a guess."
)

with st.expander("How it works"):
    st.markdown(
        "1. Ask a question, just like you would ask a person.\n"
        "2. The app finds the parts of the policy that actually answer "
        "it.\n"
        "3. It writes an answer using only what's in those parts, and "
        "tells you which page(s) it came from.\n"
        "4. If the policy doesn't cover your question, it says so "
        "instead of making something up."
    )

# --- Sidebar: mode selection ------------------------------------------------
with st.sidebar:
    st.header("Get started")
    mode = st.radio(
        "Which policy do you want to ask about?",
        options=("Bundled-policy demo", "Upload my own policy"),
        index=0,
        help=(
            "Try the sample policy to see how it works, or upload your "
            "own PDF. Your uploaded file is only used for this session "
            "and is never saved."
        ),
    )
    st.divider()
    if API_URL:
        st.caption(f"Demo served by API: {API_URL}")
    elif _api_key_present():
        st.caption("Ready to answer questions.")
    else:
        st.caption("No API key set yet — answers won't work until one is added.")
    st.caption("Free to use. Not legal or financial advice.")

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
            "**I don't know.** This policy doesn't seem to cover that, so "
            "rather than guess, here's an honest answer. Try rephrasing, or "
            "ask about something else in the document."
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
        "Trying the demo? These questions are answered from a sample "
        "insurance policy (a public specimen document), just so you can "
        "see the app in action before uploading your own."
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
        "Upload your policy as a PDF and ask away. Your file is used only "
        "for this session — it's never saved or shared."
    )

    uploaded = st.file_uploader("Your policy (PDF)", type=["pdf"])
    if uploaded is None:
        st.caption("Upload a PDF above to get started.")
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

    st.success(f"Got it — '{uploaded.name}' is ready. Ask a question below.")
    _query_ui(collection, key_prefix="upload", show_examples=False)

# --- Mode routing -----------------------------------------------------------
if mode == "Bundled-policy demo":
    render_demo_mode()
else:
    render_upload_mode()
