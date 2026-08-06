"""
Streamlit MVP for Insurance-Policy-RAG.

Thin UI layer over src/rag_pipeline.py. Two modes:
  - Bundled-policy demo: loads a pre-built, on-disk Chroma index shipped
    with the app (no embedding calls at startup -> free-tier friendly).
  - User upload: builds a per-session, in-memory ephemeral index from an
    uploaded PDF and persists nothing (privacy).

Run locally:  streamlit run app/streamlit_app.py
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

# --- Secrets / config -------------------------------------------------------
# On Streamlit Community Cloud, put GEMINI_API_KEY (and optionally
# INSURANCE_RAG_ROOT) in the app's Secrets. Mirror them into the environment
# so rag_pipeline's env-based config picks them up unchanged.
def _load_secret_into_env(key: str) -> None:
    if key not in os.environ and key in st.secrets:
        os.environ[key] = str(st.secrets[key])

for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "INSURANCE_RAG_ROOT"):
    try:
        _load_secret_into_env(_k)
    except Exception:
        # st.secrets raises if no secrets file exists locally; that's fine.
        pass

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

# --- Page config ------------------------------------------------------------
st.set_page_config(
    page_title="Insurance-Policy-RAG",
    page_icon="\U0001F4C4",
    layout="centered",
)

st.title("Insurance-Policy-RAG")
st.caption(
    "Ask natural-language questions about an insurance policy. Answers are "
    "grounded in the document, cited by page, and abstain when the policy "
    "doesn't cover the question."
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


def _render_answer(question: str, collection) -> None:
    """Run the pipeline for one question and render the grounded result."""
    with st.spinner("Retrieving and generating a grounded answer..."):
        answer, pages, retrieved = answer_question(collection, question)

    if answer.strip().lower().startswith("i don't know"):
        st.warning(
            "I don't know - the policy text retrieved does not cover this "
            "question, so the system abstains rather than guess."
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


def _query_ui(collection, key_prefix: str, show_examples: bool = True) -> None:
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

    if clicked:
        _render_answer(clicked, collection)


def render_demo_mode() -> None:
    """Bundled-policy demo: query the pre-built SAMPLE-policy index."""
    st.info(
        "Demo mode uses a pre-built index of a published, SAMPLE-watermarked "
        "policy (Manulife FlexCare). It is a stand-in for development only."
    )

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
