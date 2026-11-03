"""
Offline tests for the deployment pieces (PLAN.md M4): the API container's
inputs, the API's startup and request ids, and the app's HTTP client.
No Docker, network or API key needed (the container itself is checked in CI
by .github/workflows/docker.yml).
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _pins(path: Path) -> dict[str, str]:
    pins = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            name, version = line.split("==")
            pins[re.sub(r"\[.*\]", "", name).lower()] = version
    return pins


# --- container inputs -----------------------------------------------------------------
def test_api_requirements_are_a_subset_of_requirements_with_same_pins():
    api = _pins(REPO_ROOT / "requirements-api.txt")
    full = _pins(REPO_ROOT / "requirements.txt")
    assert api, "requirements-api.txt is empty"
    for name, version in api.items():
        assert full.get(name) == version, f"{name}: {version} vs {full.get(name)}"
    assert {"openai", "chromadb", "fastapi", "uvicorn", "httpx", "numpy"} <= set(api)
    assert "streamlit" not in api  # the API image doesn't need the UI


def test_dockerfile_basics():
    df = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.11-slim" in df
    assert "requirements-api.txt" in df
    assert re.search(r"^USER appuser$", df, re.M), "run as a non-root user"
    assert "${PORT:-8080}" in df  # Cloud Run sets PORT
    assert "COPY --chown=appuser:appuser app/demo_index/" in df
    assert "GEMINI_API_KEY" not in df  # secrets come from the environment only


def test_docker_context_allowlist_includes_what_the_image_copies():
    lines = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert lines[lines.index("*") + 1:] and "*" in lines
    for needed in ("!requirements-api.txt", "!src/", "!api/", "!app/demo_index/"):
        assert needed in lines, needed
    gcloud = (REPO_ROOT / ".gcloudignore").read_text(encoding="utf-8")
    for kept in ("src/", "api/", "app/", "Dockerfile", "requirements-api.txt"):
        assert not re.search(rf"^{re.escape(kept)}", gcloud, re.M), f"{kept} must be uploaded"
    assert ".env" in gcloud.splitlines()  # never upload local secrets


# --- API startup and request ids ----------------------------------------------------------
@pytest.fixture
def api(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from api import main as api_main

    monkeypatch.setattr(api_main, "_collection", None)
    return api_main


def test_index_is_loaded_at_startup(api, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(api, "load_persistent_collection", lambda persist_dir: object())
    with TestClient(api.app) as client:  # the with-block runs the startup hook
        assert client.get("/health").json()["index_loaded"] is True


def test_startup_survives_a_missing_index(api, monkeypatch):
    from fastapi.testclient import TestClient

    def broken(persist_dir):
        raise RuntimeError("no index")
    monkeypatch.setattr(api, "load_persistent_collection", broken)
    with TestClient(api.app) as client:
        h = client.get("/health")
        assert h.status_code == 200 and h.json()["index_loaded"] is False


def test_request_id_is_echoed_or_created(api):
    from fastapi.testclient import TestClient

    client = TestClient(api.app)
    assert client.get("/health", headers={"X-Request-ID": "abc123"}).headers[
        "X-Request-ID"] == "abc123"
    assert re.fullmatch(r"[0-9a-f]{32}", client.get("/health").headers["X-Request-ID"])


# --- the app's HTTP client -------------------------------------------------------------------
@pytest.fixture(scope="module")
def api_client():
    requests = pytest.importorskip("requests")
    spec = importlib.util.spec_from_file_location("api_client", REPO_ROOT / "app" / "api_client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.requests = requests
    return module


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def test_client_normalizes_a_good_reply(api_client):
    calls = []

    def post(url, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        return _Resp(200, {"answer": "Covered.", "pages": [7], "abstained": False,
                           "citations_verified": True,
                           "retrieved": [{"id": "doc_1", "page": 7, "score": 0.3, "text": "t"}]})
    r = api_client.ask("https://api.example/", "Is physio covered?", token="tok", post=post)
    assert calls[0][0] == "https://api.example/ask"
    assert calls[0][2] == {"Authorization": "Bearer tok"}
    assert calls[0][3] == api_client.TIMEOUT_S == 90
    assert r["answer"] == "Covered." and r["retrieved"][0]["metadata"] == {"page": 7}


@pytest.mark.parametrize("raised, expected", [
    ("timeout", "took too long"),
    ("connection", "isn't reachable"),
])
def test_client_explains_network_failures(api_client, raised, expected):
    import requests

    def post(*a, **k):
        raise requests.Timeout() if raised == "timeout" else requests.ConnectionError()
    with pytest.raises(api_client.ApiError, match=expected):
        api_client.ask("https://api.example", "q", post=post)


@pytest.mark.parametrize("status, body, expected", [
    (503, {"detail": "Gemini's request quota is used up; try again in about 13 hours."},
     "about 13 hours"),
    (401, {"detail": "Missing or invalid bearer token."}, "isn't authorized"),
    (502, ValueError("not json"), r"error \(502\)"),
])
def test_client_explains_http_errors(api_client, status, body, expected):
    with pytest.raises(api_client.ApiError, match=expected):
        api_client.ask("https://api.example", "q", post=lambda *a, **k: _Resp(status, body))


# --- failing fast and logging why (fix after the first Cloud Run deploy) -------------
def test_container_fails_fast_on_a_stuck_gemini_call():
    df = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "INSURANCE_RAG_REQUEST_TIMEOUT=20" in df and "INSURANCE_RAG_MAX_RETRIES=1" in df


def test_ask_logs_outcome_and_error_type_but_never_the_question(api, monkeypatch, caplog):
    import logging

    from fastapi.testclient import TestClient

    from src import rag_pipeline as rp

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("INSURANCE_RAG_API_TOKEN", raising=False)
    monkeypatch.setattr(api, "_get_collection", lambda: object())
    question = "Is my secret condition covered?"

    def stuck(*a, **k):
        try:
            raise TimeoutError("gemini did not answer")
        except TimeoutError as exc:
            raise rp.GeminiUnavailableError("Gemini is temporarily unavailable") from exc
    monkeypatch.setattr(api, "answer_question_detailed", stuck)
    client = TestClient(api.app)
    with caplog.at_level(logging.INFO, logger="insurance_rag.api"):
        r = client.post("/ask", json={"question": question}, headers={"X-Request-ID": "rid-1"})
    assert r.status_code == 503
    line = next(rec.getMessage() for rec in caplog.records if "ask failed" in rec.getMessage())
    assert "rid=rid-1" in line and "error=GeminiUnavailableError" in line
    assert "cause=TimeoutError" in line and "status=503" in line

    monkeypatch.setattr(api, "answer_question_detailed", lambda *a, **k: {
        "answer": "Covered.", "pages": [7], "abstained": False, "citations_verified": True,
        "retrieved": [], "generation_calls": 1})
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="insurance_rag.api"):
        assert client.post("/ask", json={"question": question}).status_code == 200
    ok = [rec.getMessage() for rec in caplog.records if "ask ok" in rec.getMessage()]
    assert ok and "generation_calls=1" in ok[0]
    assert all(question not in rec.getMessage() for rec in caplog.records)


def test_api_uses_the_fallback_and_reports_which_model_answered(api, monkeypatch):
    from fastapi.testclient import TestClient

    seen = {}

    def answered_by_backup(collection, question, k=4, **kw):
        seen.update(kw)
        return {"answer": "Covered.", "pages": [7], "abstained": False,
                "citations_verified": True, "retrieved": [], "generation_calls": 1,
                "model_used": "gemini-3.6-flash", "fallback_used": True,
                "fallback_reason": "InternalServerError"}
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("INSURANCE_RAG_API_TOKEN", raising=False)
    monkeypatch.setattr(api, "_get_collection", lambda: object())
    monkeypatch.setattr(api, "answer_question_detailed", answered_by_backup)
    client = TestClient(api.app)
    body = client.post("/ask", json={"question": "q"}).json()
    assert seen["fallback_model"] == api.GEN_FALLBACK_MODEL
    assert body["model"] == "gemini-3.6-flash" and body["fallback_used"] is True
    assert client.get("/health").json()["model_fallback"] == api.GEN_FALLBACK_MODEL


def test_client_passes_through_which_model_answered(api_client):
    reply = {"answer": "a", "pages": [], "abstained": False, "citations_verified": False,
             "retrieved": [], "model": "gemini-3.6-flash", "fallback_used": True}
    r = api_client.ask("https://api.example", "q", post=lambda *a, **k: _Resp(200, reply))
    assert r["model_used"] == "gemini-3.6-flash" and r["fallback_used"] is True


def test_root_describes_the_service(api):
    from fastapi.testclient import TestClient

    r = TestClient(api.app).get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "Insurance-Policy-RAG API" and body["endpoints"]["docs"] == "/docs"
