"""
Offline tests for src/rag_pipeline.py, src/evaluate.py and api/main.py.

No API key and no network needed: embeddings and generation are replaced by
deterministic fakes. Requires the project requirements (chromadb, fastapi,
openai, ...); run with:  pytest tests/
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

chromadb = pytest.importorskip("chromadb")

from src import evaluate as ev  # noqa: E402
from src import rag_pipeline as rp  # noqa: E402


# --- fakes -------------------------------------------------------------------
def _fake_embed(text: str) -> list[float]:
    """Tiny deterministic 'embedding': normalized letter histogram."""
    v = [0.0] * 26
    for ch in text.lower():
        if "a" <= ch <= "z":
            v[ord(ch) - 97] += 1.0
    n = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / n for x in v]


@pytest.fixture
def fake_embeddings(monkeypatch):
    monkeypatch.setattr(rp, "embed_texts", lambda texts, **_: [_fake_embed(t) for t in texts])
    monkeypatch.setattr(rp, "embed_query", lambda text, client=None: _fake_embed(text))
    monkeypatch.setattr(rp, "chunk_pages", lambda pages, source_name="policy.pdf": [
        {"id": f"doc_{i}", "text": p["text"], "page": p["page"], "source": source_name}
        for i, p in enumerate(pages)
    ])


def _fake_pages(text):
    """Stand-in for extract_pages. Chunking is stubbed separately (see the
    fixture) because the real splitter downloads the tiktoken vocabulary."""
    return lambda source: [{"page": 1, "text": text}]


# --- upload isolation (the multi-user bug) -----------------------------------
def test_uploads_get_isolated_collections(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "extract_pages", _fake_pages("Physiotherapy is covered for user A."))
    col_a, _ = rp.build_index_from_pdf(b"a", persist_dir=None)

    monkeypatch.setattr(rp, "extract_pages", _fake_pages("Dental is covered for user B."))
    col_b, _ = rp.build_index_from_pdf(b"b", persist_dir=None)

    # Distinct names, and building B did NOT delete A (it used to).
    assert col_a.name != col_b.name
    assert col_a.count() == 1 and col_b.count() == 1
    assert "user A" in col_a.get()["documents"][0]
    assert "user B" in col_b.get()["documents"][0]

    # Freeing A leaves B intact.
    rp.drop_collection(col_a)
    names = {c.name for c in chromadb.EphemeralClient(settings=rp._chroma_settings()).list_collections()}
    assert col_a.name not in names and col_b.name in names
    rp.drop_collection(col_b)
    rp.drop_collection(col_b)  # idempotent


def test_dev_path_keeps_fixed_collection_name(monkeypatch, fake_embeddings, tmp_path):
    monkeypatch.setattr(rp, "extract_pages", _fake_pages("Some policy text about claims."))
    col, _ = rp.build_index_from_pdf(b"x", persist_dir=str(tmp_path / "chroma"))
    assert col.name == rp.COLLECTION_NAME


# --- API key resolution -------------------------------------------------------
def test_google_api_key_alias(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g-key")
    assert rp._read_api_key() == "g-key"
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    assert rp._read_api_key() == "gem-key"


# --- generation edge cases ------------------------------------------------------
class _FakeCollection:
    def __init__(self, distance):
        self.distance = distance

    def query(self, **_):
        return {
            "ids": [["doc_0"]],
            "documents": [["Physiotherapy is covered."]],
            "metadatas": [[{"page": 7, "source": "policy.pdf"}]],
            "distances": [[self.distance]],
        }


def _fake_client(content, finish_reason="stop"):
    resp = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish_reason, message=SimpleNamespace(content=content))])
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **_: resp)))


def test_answer_none_content_abstains(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: _fake_client(None))
    answer, pages, retrieved = rp.answer_question(_FakeCollection(0.2), "Is physio covered?")
    assert answer == rp.IDK_ANSWER and pages == [] and len(retrieved) == 1


def test_answer_happy_path_cites_pages(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: _fake_client("Yes, it is covered."))
    answer, pages, _ = rp.answer_question(_FakeCollection(0.2), "Is physio covered?")
    assert answer == "Yes, it is covered." and pages == [7]


def test_answer_out_of_threshold_short_circuits(monkeypatch, fake_embeddings):
    def boom():
        raise AssertionError("LLM must not be called when nothing passes the threshold")
    monkeypatch.setattr(rp, "get_client", boom)
    assert rp.answer_question(_FakeCollection(0.9), "Capital of France?") == (rp.IDK_ANSWER, [], [])


# --- evaluation harness ---------------------------------------------------------
QSET = {
    "idk_answer": "I don't know",
    "in_scope": [{"id": "in_01", "question": "Is physio covered?", "expected_keywords": ["physio"]}],
    "out_of_scope": [{"id": "out_01", "question": "Capital of France?"}],
}


def _answer_fn(q):
    if "physio" in q:
        return "Physio is covered.", [7], [{"score": 0.3}]
    return "I don't know", [], []


def test_run_eval_metrics():
    _, s = ev.run_eval(QSET, _answer_fn, "idx", sleep_between=0, log=lambda _: None)
    assert s["out_of_scope_abstention_rate"] == 1.0
    assert s["in_scope_retrieval_hit_rate"] == 1.0
    assert s["in_scope_keyword_rate"] == 1.0
    assert s["in_scope_answered"] == 1 and not s["in_scope_abstained_ids"]


def test_eval_cache_invalidates_on_reworded_question():
    calls = []
    fn = lambda q: (calls.append(q), _answer_fn(q))[1]  # noqa: E731
    cache = {}
    ev.run_eval(QSET, fn, "idx", cache=cache, sleep_between=0, log=lambda _: None)
    ev.run_eval(QSET, fn, "idx", cache=cache, sleep_between=0, log=lambda _: None)
    assert len(calls) == 2  # second run fully cached

    reworded = {**QSET, "in_scope": [{**QSET["in_scope"][0], "question": "Is physio covered at all?"}]}
    ev.run_eval(reworded, fn, "idx", cache=cache, sleep_between=0, log=lambda _: None)
    assert calls[-1] == "Is physio covered at all?" and len(calls) == 3

    ev.run_eval(QSET, fn, "other_index", cache=cache, sleep_between=0, log=lambda _: None)
    assert len(calls) == 5  # different index -> re-run everything


# --- shipped demo index ---------------------------------------------------------
def test_demo_index_opens(tmp_path):
    # Open a COPY: Chroma rewrites HNSW files on open, which would dirty the
    # committed index in the working tree.
    import shutil

    idx = tmp_path / "demo_index"
    shutil.copytree(REPO_ROOT / "app" / "demo_index", idx)
    col = rp.load_persistent_collection(persist_dir=str(idx))
    assert col.count() > 0
    got = col.get(limit=1, include=["metadatas", "embeddings"])
    assert "page" in got["metadatas"][0]
    assert len(got["embeddings"][0]) == 3072  # gemini-embedding-001


# --- API ------------------------------------------------------------------------
def test_api_health_and_ask(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from api import main as api_main

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setattr(api_main, "_get_collection", lambda: object())
    monkeypatch.setattr(api_main, "answer_question", lambda c, q, k: (
        ("I don't know", [], []) if "France" in q else
        ("Covered.", [7], [{"id": "doc_0", "text": "t", "metadata": {"page": 7}, "score": 0.3}])))

    client = fastapi_testclient.TestClient(api_main.app)
    assert client.get("/health").json()["api_key_present"] is True

    r = client.post("/ask", json={"question": "Is physio covered?"}).json()
    assert r["answer"] == "Covered." and r["pages"] == [7] and r["abstained"] is False

    r = client.post("/ask", json={"question": "Capital of France?"}).json()
    assert r["abstained"] is True

    assert client.post("/ask", json={"question": ""}).status_code == 422
