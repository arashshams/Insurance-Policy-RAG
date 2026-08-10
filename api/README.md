# API backend — Insurance-Policy-RAG

A FastAPI service (`api/main.py`) that exposes the same retrieval +
grounded-generation pipeline (`src/rag_pipeline.py`) over HTTP. It answers
questions about the bundled, SAMPLE-watermarked demo policy and returns answers
grounded in the document, cited by page, and abstaining when the policy does not
cover the question.

For the project as a whole, see the [top-level README](../README.md). For the
Streamlit UI, see [app/README.md](../app/README.md).

## Endpoints

| Method | Path      | Purpose |
| ------ | --------- | ------- |
| GET    | `/health` | Readiness probe: service status, whether the demo index and an API key are present. Never calls the LLM. |
| POST   | `/ask`    | Ask a question; returns a grounded, page-cited answer. |

Interactive docs are served by FastAPI at `/docs` (Swagger) and `/redoc`.

### `POST /ask`

Request body:

```json
{
  "question": "Is physiotherapy covered?",
  "k": 4
}
```

- `question` (string, required) — the natural-language question.
- `k` (int, optional, default 4, range 1-20) — how many chunks to retrieve.

Response body:

```json
{
  "answer": "Yes. Physiotherapy is covered ...",
  "pages": [7, 8],
  "abstained": false,
  "retrieved": [
    {"id": "doc_12", "page": 7, "score": 0.28, "text": "..."}
  ]
}
```

- `abstained` is `true` when nothing passed the relevance threshold (the
  answer is then "I don't know" and `retrieved` is empty). This is the
  guardrail working as designed for out-of-scope questions.

## Run locally

From the repository root, with dependencies installed and a key set:

```bash
pip install -r requirements.txt
export GEMINI_API_KEY="your-key"     # PowerShell: $env:GEMINI_API_KEY="your-key"
uvicorn api.main:app --reload
```

Then, in another shell:

```bash
curl localhost:8000/health

curl -X POST localhost:8000/ask \\
  -H "content-type: application/json" \\
  -d '{"question": "Is physiotherapy covered?"}'
```

## Configuration

All configuration is via environment variables (the pipeline reads them too):

- `GEMINI_API_KEY` (required) — key for embeddings + generation. Without it,
  `/ask` returns HTTP 503 and `/health` reports `api_key_present: false`.
- `DEMO_INDEX_DIR` (optional) — path to the pre-built Chroma index. Defaults
  to `app/demo_index/` in the repo.
- `INSURANCE_RAG_GEN_MODEL` / `INSURANCE_RAG_THRESHOLD` / `INSURANCE_RAG_K`
  etc. — same overrides as the pipeline (see `src/rag_pipeline.py`).

The demo index must be present for `/ask` to work; if it is missing the
endpoint returns HTTP 503 with a message pointing at `app/README.md`.

## Deploy (free tier)

The service is a standard ASGI app (`api.main:app`), so it runs on any host
that can run `uvicorn`. Candidate free tiers (verify current limits before
choosing): Hugging Face Spaces, Render, Fly.io.

General steps:

1. Point the host at this repo and install `requirements.txt`.
2. Start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`.
3. Set `GEMINI_API_KEY` as a secret/environment variable on the host.
4. Ensure `app/demo_index/` ships with the deploy (it is committed to the repo).

## Notes

- The served corpus is the published SAMPLE-watermarked policy only; no real
  policy contents are involved.
- The index is opened once at process startup and reused; requests persist
  nothing.
