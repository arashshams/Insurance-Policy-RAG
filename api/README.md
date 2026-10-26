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
| GET    | `/health` | Readiness probe: service status, whether the demo index and an API key are present, and whether `/ask` requires a token. Never calls the LLM. Always open. |
| POST   | `/ask`    | Ask a question; returns a grounded, page-cited answer. Requires a bearer token when `INSURANCE_RAG_API_TOKEN` is set. |

Interactive docs are served by FastAPI at `/docs` (Swagger) and `/redoc`.

### `POST /ask`

Request body:

```json
{
  "question": "Is physiotherapy covered?",
  "k": 4
}
```

- `question` (string, required, 1-1000 characters by default) — the natural-language question.
- `k` (int, optional, default 4, range 1-20) — how many chunks to retrieve.

Response body:

```json
{
  "answer": "Yes. Physiotherapy is covered ...",
  "pages": [10],
  "abstained": false,
  "citations_verified": true,
  "retrieved": [
    {"id": "doc_9", "page": 10, "score": 0.28, "text": "..."}
  ]
}
```

- `abstained` is `true` when the system said "I don't know": either nothing
  passed the relevance threshold (then `retrieved` is empty and no LLM call
  was made) or the model found no answer in the retrieved passages. It uses
  the same `is_abstention` rule as the app and the evaluation harness. `pages`
  is empty whenever `abstained` is `true`.
- `pages` are the pages of the passages the model cited. If the model cited
  none, `citations_verified` is `false` and `pages` lists the pages of every
  retrieved passage instead.

Errors: `401` missing/invalid token (when one is configured), `422` invalid
body (e.g. an empty or too-long question), `429` rate limited (honor the
`Retry-After` header), `502` pipeline error, `503` no API key, no index, or
Gemini still overloaded / rate-limited after the pipeline's retries (with
`Retry-After: 60`).

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

curl -X POST localhost:8000/ask \
  -H "content-type: application/json" \
  -d '{"question": "Is physiotherapy covered?"}'

# if INSURANCE_RAG_API_TOKEN is set on the server:
curl -X POST localhost:8000/ask \
  -H "content-type: application/json" \
  -H "Authorization: Bearer $INSURANCE_RAG_API_TOKEN" \
  -d '{"question": "Is physiotherapy covered?"}'
```

## Configuration

All configuration is via environment variables (the pipeline reads them too):

- `GEMINI_API_KEY` (required) — key for embeddings + generation. Without it,
  `/ask` returns HTTP 503 and `/health` reports `api_key_present: false`.
- `INSURANCE_RAG_API_TOKEN` (optional, **strongly recommended when public**) —
  if set, `/ask` requires `Authorization: Bearer <token>`. Without it, anyone
  who finds the URL can spend your Gemini quota. If the Streamlit app calls
  the API, give it the same value (it sends the header automatically).
- `INSURANCE_RAG_API_RATE_PER_CLIENT` / `INSURANCE_RAG_API_RATE_GLOBAL`
  (optional, default 10 / 60 requests per minute; `0` disables) — rate limits.
  The per-client key is the connecting address; behind a reverse proxy that is
  the proxy itself, so the per-client limit then acts as a second global limit.
- `INSURANCE_RAG_MAX_QUESTION_CHARS` (optional, default 1000) — question length cap.
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
3. Set `GEMINI_API_KEY` and `INSURANCE_RAG_API_TOKEN` as secrets/environment
   variables on the host.
4. Ensure `app/demo_index/` ships with the deploy (it is committed to the repo).

## Notes

- The served corpus is the published SAMPLE-watermarked policy only; no real
  policy contents are involved.
- The index is opened once at process startup and reused; requests persist
  nothing.
