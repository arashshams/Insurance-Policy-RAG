# Container for the FastAPI backend (api/main.py), PLAN.md M4.
# Serves the bundled SAMPLE demo index; the Gemini key and API token come from
# environment variables at run time (Secret Manager on Cloud Run), never from
# the image.
#   docker build -t insurance-rag-api .
#   docker run --rm -p 8080:8080 --env-file .env insurance-rag-api
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Dependencies first, so code changes don't reinstall them.
COPY requirements-api.txt .
RUN pip install -r requirements-api.txt

# Run as an unprivileged user. ChromaDB rewrites index files when it opens
# them, so that user owns the copied index.
RUN useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser src/ src/
COPY --chown=appuser:appuser api/ api/
COPY --chown=appuser:appuser app/demo_index/ app/demo_index/
USER appuser

# Fail fast on a stuck Gemini call: at most 20 s per attempt and one retry
# (about 42 s per call in the worst case), so the API answers with a clear
# 503 well before Cloud Run's request timeout (120 s) and the app's (60 s).
# With the fallback model, the main model's single attempt gets 8 s before the
# backup answers (PLAN.md D19): outages cost ~10 s per answer instead of ~20.
ENV INSURANCE_RAG_ROOT=/srv \
    PORT=8080 \
    INSURANCE_RAG_REQUEST_TIMEOUT=20 \
    INSURANCE_RAG_MAX_RETRIES=1 \
    INSURANCE_RAG_PRIMARY_TIMEOUT=8
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT', '8080'), timeout=4)"

# Cloud Run sets PORT. --proxy-headers takes the client address from the
# X-Forwarded-For header added by the platform's front end, so the API's
# per-client rate limit sees visitors instead of the proxy (the global limit
# applies either way). --no-access-log: uvicorn's access log would print each
# visitor's IP address; the API's own JSON line per question replaces it
# (PLAN.md M5).
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*' --no-access-log"]
