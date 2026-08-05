"""
Streamlit MVP for Insurance-Policy-RAG.

Thin UI layer over src/rag_pipeline.py. Two modes:
  - Bundled-policy demo: loads a pre-built, on-disk Chroma index shipped
      with the app (no embedding calls at startup -> free-tier friendly).
        - User upload: builds a per-session, in-memory ephemeral index from an
            uploaded PDF and persists nothing (privacy).

            Run locally:  streamlit run app/streamlit_app.py
            """

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

# --- Mode routing (implemented in later commits) ---------------------------
if mode == "Bundled-policy demo":
      st.info("Bundled-policy demo - coming in the next commit.")
else:
      st.info("Upload mode - coming in a later commit.")
  
