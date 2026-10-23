# Streamlit app — Insurance-Policy-RAG

A thin Streamlit UI over `src/rag_pipeline.py`. It lets you ask natural-language
questions about an insurance policy and returns answers that are grounded in the
document, cited by page, and that abstain ("I don't know") when the policy does
not cover the question.

For the project as a whole (architecture, evaluation, pipeline interface), see
the [top-level README](../README.md).

## Two modes

- **Bundled-policy demo** — loads a pre-built, on-disk Chroma index shipped in
  `app/demo_index/`. No embedding calls happen at startup, which keeps cold
  starts fast and free-tier friendly. The bundled policy is a published,
  SAMPLE-watermarked Manulife FlexCare document used as a development stand-in.
- **Upload my own policy** — builds a per-session, in-memory (ephemeral) index
  from an uploaded PDF. Nothing is written to disk and nothing is persisted
  across sessions. Each upload gets its own uniquely named collection, tracked
  in a process-wide registry (`src/guardrails.py`) and referenced by name from
  that browser session's `st.session_state`, so concurrent visitors on the same
  app process can't see or delete each other's index. A session's previous
  upload is freed when it uploads a new file, and any upload left idle for
  `INSURANCE_RAG_UPLOAD_TTL_MIN` minutes (default 30) is freed on the next
  visit to the app, so abandoned sessions don't accumulate in memory. The
  upload's text is sent to the Gemini API (see [Privacy](#privacy)), and
  answers use `INSURANCE_RAG_UPLOAD_THRESHOLD` (defaults to the 0.37 that was
  calibrated on the sample policy; the UI notes it may not fit other documents).

## Cost controls

Every question and upload spends the deployer's Gemini quota, so the app
enforces limits (all environment variables / Secrets):

| Limit | Default | Variable |
| --- | --- | --- |
| Upload size | 10 MB | `INSURANCE_RAG_MAX_UPLOAD_MB` (+ `server.maxUploadSize` in `.streamlit/config.toml`) |
| Upload pages / chunks | 60 / 150 | `INSURANCE_RAG_MAX_UPLOAD_PAGES` / `INSURANCE_RAG_MAX_UPLOAD_CHUNKS` |
| Questions per session / app-wide | 10 / 60 per minute | `INSURANCE_RAG_APP_Q_PER_SESSION` / `INSURANCE_RAG_APP_Q_GLOBAL` |
| Uploads per session / app-wide | 3 / 30 per hour | `INSURANCE_RAG_APP_UPLOADS_PER_SESSION` / `INSURANCE_RAG_APP_UPLOADS_GLOBAL` |
| Concurrent upload indexes | 20 | `INSURANCE_RAG_MAX_UPLOAD_INDEXES` |
| Idle upload lifetime | 30 min | `INSURANCE_RAG_UPLOAD_TTL_MIN` |

Oversized PDFs are rejected before any embedding call. Set a limit to `0` to
disable it. Limits are per app process, which on Streamlit Community Cloud
means per app.

## Run locally

From the repository root:

```bash
# 1. install dependencies (Python 3.11 recommended)
pip install -r requirements.txt

# 2. provide a Gemini API key (used for embeddings + generation)
export GEMINI_API_KEY="your-key"        # Windows PowerShell: $env:GEMINI_API_KEY="your-key"

# 3. launch
python -m streamlit run app/streamlit_app.py
```

Without a key, the UI still loads but answers are disabled (the sidebar shows a
"No GEMINI_API_KEY set" hint and the Ask button reports the missing key).

## Deploy on Streamlit Community Cloud

1. Push the branch to GitHub (the app reads `app/demo_index/` from the repo, so
   make sure the demo index is committed — see below).
2. On [share.streamlit.io](https://share.streamlit.io), create a new app pointing
   at this repo/branch with `app/streamlit_app.py` as the entry point.
3. In the app's **Settings -> Secrets**, add your key in TOML form:

   ```toml
   GEMINI_API_KEY = "your-key"
   ```

   The app mirrors recognized secrets into environment variables at startup, so
   `rag_pipeline`'s env-based config picks them up unchanged. `GOOGLE_API_KEY`,
   `INSURANCE_RAG_ROOT`, `INSURANCE_RAG_API_URL` and `INSURANCE_RAG_API_TOKEN`
   (sent as a bearer token when the demo is served by the API) are also
   honored if present.
4. Deploy. Demo mode works immediately; upload mode works once a key is set.

Locally, secrets are optional: the app only reads `st.secrets` when a
`secrets.toml` actually exists (`~/.streamlit/secrets.toml` or
`.streamlit/secrets.toml`), so a plain `GEMINI_API_KEY` env var is enough and no
"No secrets files found" warning is printed.

## Regenerating the demo index

Demo mode needs the pre-built index at `app/demo_index/` (a binary Chroma store:
a `chroma.sqlite3` plus a UUID-named subfolder). It is committed to the repo so
Streamlit Cloud can load it without re-embedding on every cold start.

To rebuild it from the SAMPLE-watermarked policy PDF:

```python
from pathlib import Path
from src.rag_pipeline import build_index_from_pdf, COLLECTION_NAME

collection, chunks = build_index_from_pdf(
    "path/to/flexcare_SAMPLE.pdf",
    persist_dir=str(Path("app") / "demo_index"),
    collection_name=COLLECTION_NAME,      # insurance_policy_cvdb
    source_name="flexcare_SAMPLE.pdf",
)
print(len(chunks), collection.count())
```

Then commit the folder:

```bash
git add app/demo_index
git commit -m "Update pre-built demo index"
```

Notes:
- Only the **published SAMPLE-watermarked** policy is ever committed. The real
  policy PDF must never be embedded into a committed index.
- The chunk count is environment-sensitive by about one chunk: calibration on
  Colab produced **37** chunks, while a local Python 3.11 build produced **38**,
  because the tokenizer / PDF-extractor versions differ slightly. Both are valid
  for the same on-spec settings (cl100k_base / 800 / 128).
- Before rebuilding, delete the old `app/demo_index/` so old and new vectors do
  not mix. On Windows, stop the running app and shut down any notebook kernel
  first, or the Chroma files stay locked and cannot be replaced.

## Privacy

Uploaded PDFs are never written to disk; their in-memory index is freed when
the user switches files or after the idle TTL. To embed the policy and answer
questions, however, the policy text and each question are sent to Google's
Gemini API. On the Gemini free tier, Google may use submitted content to
improve its products, and the upload screen tells users this before they
upload. Use a paid-tier key, or don't offer upload mode, if real personal data
is involved.

The committed demo index is built solely from the published,
SAMPLE-watermarked stand-in policy — no real policy contents are in the repo.
