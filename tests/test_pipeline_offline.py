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
    return lambda source, max_pages=None: [{"page": 1, "text": text}]


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
    """Returns doc_0 (page 7) at `distance` and, optionally, doc_1 (page 9)."""

    def __init__(self, distance, second_distance=None):
        self.distance = distance
        self.second_distance = second_distance

    def query(self, **_):
        ids, docs, metas, dists = ["doc_0"], ["Physiotherapy is covered."], \
            [{"page": 7, "source": "policy.pdf"}], [self.distance]
        if self.second_distance is not None:
            ids.append("doc_1")
            docs.append("Dental is excluded on some plans.")
            metas.append({"page": 9, "source": "policy.pdf"})
            dists.append(self.second_distance)
        return {"ids": [ids], "documents": [docs], "metadatas": [metas],
                "distances": [dists]}


def _fake_client(content, finish_reason="stop", model=None):
    resp = SimpleNamespace(model=model, choices=[SimpleNamespace(
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




# --- abstention: one shared definition ------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("I don't know", True),
    ("I don't know.", True),
    ("i DON'T know", True),
    ("I don’t know.", True),          # curly apostrophe
    ('"I don\'t know"', True),
    ("I don't know [doc_3]", True),        # stray citation tag
    ("I don't know the exact amount, but physiotherapy is covered.", False),
    ("Physiotherapy is covered.", False),
    ("", False),
])
def test_is_abstention_single_definition(text, expected):
    assert rp.is_abstention(text) is expected
    assert ev.is_abstention(text) is expected  # evaluator delegates to the same rule


# --- citations come from the chunks the model cited ----------------------------
def test_extract_citations_strips_tags_and_ignores_unknown_ids():
    clean, ids = rp.extract_citations(
        "Physio is covered [doc_1]. Dental too [doc_2, doc_9] .", ["doc_1", "doc_2"])
    assert clean == "Physio is covered. Dental too."
    assert ids == ["doc_1", "doc_2"]  # doc_9 was never in the context

    clean, ids = rp.extract_citations("Covered (doc_2)[doc_1].", ["doc_1", "doc_2"])
    assert clean == "Covered." and ids == ["doc_2", "doc_1"]


def test_pages_come_from_cited_chunks_only(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: _fake_client("Physiotherapy is covered [doc_0]."))
    r = rp.answer_question_detailed(_FakeCollection(0.2, 0.3), "Is physio covered?")
    assert r["answer"] == "Physiotherapy is covered."
    assert r["pages"] == [7] and r["cited_ids"] == ["doc_0"]
    assert r["citations_verified"] is True and r["abstained"] is False
    assert len(r["retrieved"]) == 2  # page 9 was retrieved but not cited


def test_uncited_answer_falls_back_to_all_retrieved_pages(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: _fake_client("Yes, it is covered."))
    r = rp.answer_question_detailed(_FakeCollection(0.2, 0.3), "Is physio covered?")
    assert r["pages"] == [7, 9] and r["citations_verified"] is False


def test_model_abstention_has_no_pages(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: _fake_client("I don't know."))
    answer, pages, retrieved = rp.answer_question(_FakeCollection(0.2), "Is physio covered?")
    assert answer == rp.IDK_ANSWER and pages == [] and len(retrieved) == 1


# --- calibration / reproducibility metadata ------------------------------------
def test_nearest_distance_reported_even_when_abstaining(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: (_ for _ in ()).throw(AssertionError("no LLM")))
    r = rp.answer_question_detailed(_FakeCollection(0.45, 0.52), "Capital of France?")
    assert r["abstained"] and r["retrieved"] == []
    assert r["nearest_distance"] == pytest.approx(0.45)
    # Every top-k chunk is reported before the threshold, without its text.
    assert r["candidates"] == [
        {"id": "doc_0", "page": 7, "distance": pytest.approx(0.45)},
        {"id": "doc_1", "page": 9, "distance": pytest.approx(0.52)},
    ]


def test_candidates_include_chunks_dropped_by_threshold(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: _fake_client("Covered [doc_0]."))
    r = rp.answer_question_detailed(_FakeCollection(0.2, 0.5), "Is physio covered?")
    assert [h["id"] for h in r["retrieved"]] == ["doc_0"]
    assert [c["id"] for c in r["candidates"]] == ["doc_0", "doc_1"]


def test_threshold_is_overridable_per_call(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: _fake_client("Covered [doc_0]."))
    r = rp.answer_question_detailed(_FakeCollection(0.40), "q", threshold=0.42)
    assert not r["abstained"] and r["threshold"] == 0.42


def test_resolved_model_is_recorded(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client",
                        lambda: _fake_client("Covered [doc_0].", model="gemini-9.9-flash-001"))
    r = rp.answer_question_detailed(_FakeCollection(0.2), "q")
    assert r["model_resolved"] == "gemini-9.9-flash-001"


# --- upload size caps --------------------------------------------------------------
def _blank_pdf(n_pages):
    import io
    from pypdf import PdfWriter

    w = PdfWriter()
    for _ in range(n_pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    buf.seek(0)
    return buf


def test_page_cap_rejects_before_extraction():
    with pytest.raises(rp.DocumentTooLargeError):
        rp.extract_pages(_blank_pdf(3), max_pages=2)
    assert len(rp.extract_pages(_blank_pdf(2), max_pages=2)) == 2


def test_chunk_cap_rejects_before_embedding(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "extract_pages", lambda source, max_pages=None: [
        {"page": i, "text": f"page {i} text"} for i in range(1, 6)])
    monkeypatch.setattr(rp, "embed_texts", lambda *a, **k: pytest.fail("embedded anyway"))
    with pytest.raises(rp.DocumentTooLargeError):
        rp.build_index_from_pdf(b"x", persist_dir=None, max_chunks=3)


# --- guardrails ----------------------------------------------------------------
from src import guardrails as gr  # noqa: E402


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_rate_limiter_sliding_window():
    clock = _Clock()
    lim = gr.RateLimiter(2, 60, clock=clock)
    assert lim.allow("a")[0] and lim.allow("a")[0]
    ok, retry = lim.allow("a")
    assert not ok and 0 < retry <= 60
    assert lim.allow("b")[0]  # keys are independent
    clock.t += 61
    assert lim.allow("a")[0]
    assert gr.RateLimiter(0, 60).allow("x")[0]  # 0 disables


def test_upload_registry_frees_idle_collections(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "extract_pages", _fake_pages("Physio is covered."))
    clock = _Clock()
    reg = gr.UploadIndexRegistry(dropper=rp.drop_collection, ttl_s=600,
                                 max_entries=2, clock=clock)
    col_a, _ = rp.build_index_from_pdf(b"a", persist_dir=None)
    col_b, _ = rp.build_index_from_pdf(b"b", persist_dir=None)
    name_a, name_b = reg.add(col_a), reg.add(col_b)
    assert not reg.has_capacity()  # cap reached

    clock.t += 500
    assert reg.get(name_b) is col_b  # B is in use -> its idle timer resets
    clock.t += 200                   # A idle 700s > TTL; B idle 200s
    assert reg.sweep() == [name_a]
    assert reg.get(name_a) is None and reg.get(name_b) is col_b
    live = {c.name for c in chromadb.EphemeralClient(settings=rp._chroma_settings()).list_collections()}
    assert name_a not in live and name_b in live  # really freed from memory
    assert reg.has_capacity()
    reg.remove(name_b)
    assert len(reg) == 0


# --- evaluation harness: page metrics, margins, cache expiry ---------------------
PAGED_QSET = {
    "idk_answer": "I don't know",
    "in_scope": [
        {"id": "in_01", "question": "Is physio covered?", "expected_keywords": ["physio"],
         "expected_pages": [7]},
        {"id": "in_02", "question": "Is dental covered?", "expected_keywords": ["dental"],
         "expected_pages": [11]},
    ],
    "out_of_scope": [{"id": "out_01", "question": "Capital of France?"}],
}


def _detailed_fn(q):
    chunk = lambda page, d: {"id": f"doc_{page}", "text": "t",  # noqa: E731
                             "metadata": {"page": page}, "score": d}
    if "physio" in q:
        return {"answer": "Physio is covered.", "pages": [7], "retrieved": [chunk(7, 0.25)],
                "abstained": False, "citations_verified": True, "nearest_distance": 0.25,
                "model_resolved": "m-1"}
    if "dental" in q:  # retrieved the right page, but cited the wrong one
        return {"answer": "Dental is covered.", "pages": [12],
                "retrieved": [chunk(11, 0.30), chunk(12, 0.31)], "abstained": False,
                "citations_verified": True, "nearest_distance": 0.30, "model_resolved": "m-1"}
    return {"answer": "I don't know", "pages": [], "retrieved": [], "abstained": True,
            "citations_verified": False, "nearest_distance": 0.44, "model_resolved": None}


def test_eval_page_metrics_and_threshold_suggestion():
    _, s = ev.run_eval(PAGED_QSET, _detailed_fn, "idx", sleep_between=0, log=lambda _: None)
    assert s["in_scope_retrieval_page_rate"] == 1.0
    assert s["in_scope_citation_page_rate"] == 0.5
    assert s["in_scope_page_miss_ids"] == ["in_02"]
    m = s["distance_margin"]
    assert m["separable"] and m["in_scope_max"] == 0.30 and m["out_of_scope_min"] == 0.44
    assert m["suggested_threshold"] == 0.37
    assert s["models_resolved"] == ["m-1"]
    assert "Suggested threshold" in ev.format_summary(s, "idx")


def test_eval_cache_expires(monkeypatch):
    clock = _Clock()
    calls = []
    fn = lambda q: (calls.append(q), _answer_fn(q))[1]  # noqa: E731
    cache = {}
    kw = dict(sleep_between=0, log=lambda _: None, clock=clock, max_age_days=1)
    ev.run_eval(QSET, fn, "idx", cache=cache, **kw)
    ev.run_eval(QSET, fn, "idx", cache=cache, **kw)
    assert len(calls) == 2           # fresh -> cached
    clock.t += 2 * 86400
    ev.run_eval(QSET, fn, "idx", cache=cache, **kw)
    assert len(calls) == 4           # older than max age -> re-run


# --- API ------------------------------------------------------------------------
def _fake_detailed(c, q, k=4):
    if "France" in q:
        return {"answer": "I don't know", "pages": [], "retrieved": [], "abstained": True,
                "citations_verified": False}
    return {"answer": "Covered.", "pages": [7], "abstained": False, "citations_verified": True,
            "retrieved": [{"id": "doc_0", "text": "t", "metadata": {"page": 7}, "score": 0.3}]}


@pytest.fixture
def api_client(monkeypatch):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from api import main as api_main

    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("INSURANCE_RAG_API_TOKEN", raising=False)
    monkeypatch.setattr(api_main, "_get_collection", lambda: object())
    monkeypatch.setattr(api_main, "answer_question_detailed", _fake_detailed)
    monkeypatch.setattr(api_main, "_client_limiter", gr.RateLimiter(100, 60))
    monkeypatch.setattr(api_main, "_global_limiter", gr.RateLimiter(100, 60))
    return api_main, fastapi_testclient.TestClient(api_main.app)


def test_api_health_and_ask(api_client):
    _, client = api_client
    health = client.get("/health").json()
    assert health["api_key_present"] is True and health["auth_required"] is False

    r = client.post("/ask", json={"question": "Is physio covered?"}).json()
    assert r["answer"] == "Covered." and r["pages"] == [7]
    assert r["abstained"] is False and r["citations_verified"] is True

    r = client.post("/ask", json={"question": "Capital of France?"}).json()
    assert r["abstained"] is True

    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "x" * 5000}).status_code == 422


def test_api_bearer_token(api_client, monkeypatch):
    _, client = api_client
    monkeypatch.setenv("INSURANCE_RAG_API_TOKEN", "s3cret")
    body = {"question": "Is physio covered?"}
    assert client.get("/health").json()["auth_required"] is True
    assert client.post("/ask", json=body).status_code == 401
    assert client.post("/ask", json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post("/ask", json=body, headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_api_rate_limit(api_client, monkeypatch):
    api_main, client = api_client
    monkeypatch.setattr(api_main, "_client_limiter", gr.RateLimiter(2, 60))
    body = {"question": "Is physio covered?"}
    assert client.post("/ask", json=body).status_code == 200
    assert client.post("/ask", json=body).status_code == 200
    r = client.post("/ask", json=body)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


# --- transient Gemini errors are retried ------------------------------------------
def _openai_error(cls, status):
    import httpx

    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    return cls("boom", response=httpx.Response(status, request=req), body=None)


class _Flaky:
    """Callable that raises the given errors in order, then returns `result`."""

    def __init__(self, errors, result):
        self.errors, self.result, self.calls = list(errors), result, 0

    def __call__(self, **_):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.result


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(rp.time, "sleep", lambda s: None)


def test_generation_retries_overload_then_succeeds(monkeypatch, fake_embeddings, no_sleep):
    import openai

    resp = SimpleNamespace(model=None, choices=[SimpleNamespace(
        finish_reason="stop", message=SimpleNamespace(content="Covered [doc_0]."))])
    flaky = _Flaky([_openai_error(openai.InternalServerError, 503),
                    openai.APIConnectionError(request=None)], resp)
    monkeypatch.setattr(rp, "get_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=flaky))))
    r = rp.answer_question_detailed(_FakeCollection(0.2), "Is physio covered?")
    assert r["answer"] == "Covered." and flaky.calls == 3


def test_embedding_retries_overload(no_sleep):
    import openai

    data = SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])])
    flaky = _Flaky([_openai_error(openai.InternalServerError, 503)], data)
    client = SimpleNamespace(embeddings=SimpleNamespace(create=flaky))
    assert rp.embed_query("q", client=client) == [0.1, 0.2] and flaky.calls == 2
    flaky2 = _Flaky([_openai_error(openai.RateLimitError, 429)], data)
    client2 = SimpleNamespace(embeddings=SimpleNamespace(create=flaky2))
    assert rp.embed_texts(["a"], client=client2) == [[0.1, 0.2]] and flaky2.calls == 2


def test_persistent_overload_raises_friendly_error(monkeypatch, no_sleep):
    import openai

    monkeypatch.setattr(rp, "QUERY_MAX_RETRIES", 2)
    errors = [_openai_error(openai.InternalServerError, 503) for _ in range(5)]
    flaky = _Flaky(errors, None)
    with pytest.raises(rp.GeminiUnavailableError, match="temporarily unavailable"):
        rp._call_with_backoff(flaky, "generation")
    assert flaky.calls == 3  # first try + 2 retries


def test_non_transient_errors_are_not_retried(no_sleep):
    import openai

    flaky = _Flaky([_openai_error(openai.AuthenticationError, 401)], "ok")
    with pytest.raises(openai.AuthenticationError):
        rp._call_with_backoff(flaky, "generation")
    assert flaky.calls == 1


def test_api_maps_gemini_outage_to_503(api_client, monkeypatch):
    api_main, client = api_client

    def down(*a, **k):
        raise rp.GeminiUnavailableError("Gemini is temporarily unavailable")
    monkeypatch.setattr(api_main, "answer_question_detailed", down)
    r = client.post("/ask", json={"question": "Is physio covered?"})
    assert r.status_code == 503 and r.headers["Retry-After"] == "60"


# --- evaluation: re-scoring and how abstentions happened ------------------------
def test_cached_records_are_rescored_with_current_keywords():
    calls = []
    fn = lambda q: (calls.append(q), _answer_fn(q))[1]  # noqa: E731
    cache = {}
    qset = {**QSET, "in_scope": [{**QSET["in_scope"][0], "expected_keywords": ["dental"]}]}
    _, s = ev.run_eval(qset, fn, "idx", cache=cache, sleep_between=0, log=lambda _: None)
    assert s["in_scope_keyword_rate"] == 0.0

    # Fix the expected keywords only: no new API call, and the score changes.
    _, s = ev.run_eval(QSET, fn, "idx", cache=cache, sleep_between=0, log=lambda _: None)
    assert len(calls) == 2 and s["in_scope_keyword_rate"] == 1.0


def test_summary_separates_threshold_and_model_refusals():
    def fn(q):
        if "physio" in q:
            return {"answer": "Physio is covered.", "pages": [7], "abstained": False,
                    "retrieved": [{"metadata": {"page": 7}, "score": 0.34}],
                    "citations_verified": True, "nearest_distance": 0.34}
        if "France" in q:  # threshold: nothing retrieved
            return {"answer": "I don't know", "pages": [], "retrieved": [], "abstained": True,
                    "nearest_distance": 0.50}
        # near-miss: passed the threshold, model refused
        return {"answer": "I don't know", "pages": [], "abstained": True,
                "retrieved": [{"metadata": {"page": 3}, "score": 0.33}], "nearest_distance": 0.33}

    qset = {**QSET, "out_of_scope": QSET["out_of_scope"] + [{"id": "out_02", "question": "Vet bills?"}]}
    logs = []
    _, s = ev.run_eval(qset, fn, "idx", sleep_between=0, log=logs.append)
    assert s["out_of_scope_threshold_ids"] == ["out_01"]
    assert s["out_of_scope_model_refused_ids"] == ["out_02"]
    assert s["distance_margin"]["separable"] is False
    text = ev.format_summary(s, "idx")
    assert "1 / 1 of 2" in text and "the model's refusal caught the rest" in text
    assert any("(model refused)" in line for line in logs)
    assert any("(threshold)" in line for line in logs)


# --- daily quota: fail fast, budget the evaluation --------------------------------
def _quota_error(delay="48341s", quota_id="GenerateRequestsPerDayPerProjectPerModel-FreeTier"):
    """A 429 shaped like Gemini's free-tier quota error (body is a JSON list)."""
    import httpx
    import openai

    req = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    body = [{"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
         "violations": [{"quotaId": quota_id}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay},
    ]}}]
    return openai.RateLimitError(f"Error code: 429 - {body}",
                                 response=httpx.Response(429, request=req), body=body)


def test_daily_quota_fails_fast_without_retrying(monkeypatch):
    slept = []
    monkeypatch.setattr(rp.time, "sleep", slept.append)
    flaky = _Flaky([_quota_error()], "ok")
    with pytest.raises(rp.GeminiQuotaExhaustedError) as err:
        rp._call_with_backoff(flaky, "generation")
    assert flaky.calls == 1 and slept == []  # no retries, no waiting
    assert err.value.retry_after_s == 48341 and "about 13 hours" in str(err.value)
    assert isinstance(err.value, rp.GeminiUnavailableError)  # old handlers still catch it


def test_long_quota_delay_fails_fast_but_short_rate_limit_is_retried(no_sleep):
    flaky = _Flaky([_quota_error(delay="900s", quota_id="RequestsPerHour")], "ok")
    with pytest.raises(rp.GeminiQuotaExhaustedError, match="about 15 minutes"):
        rp._call_with_backoff(flaky, "embedding")
    flaky = _Flaky([_quota_error(
        delay="20s", quota_id="GenerateRequestsPerMinutePerProjectPerModel-FreeTier")], "ok")
    assert rp._call_with_backoff(flaky, "generation") == "ok" and flaky.calls == 2


def test_client_leaves_retries_to_the_pipeline(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    assert rp.get_client().max_retries == 0


def test_generation_calls_are_counted(monkeypatch, fake_embeddings):
    monkeypatch.setattr(rp, "get_client", lambda: _fake_client("Covered [doc_0]."))
    assert rp.answer_question_detailed(_FakeCollection(0.2), "q")["generation_calls"] == 1
    monkeypatch.setattr(rp, "get_client",
                        lambda: _fake_client("Covered [doc_0].", finish_reason="length"))
    assert rp.answer_question_detailed(_FakeCollection(0.2), "q")["generation_calls"] == 2
    assert rp.answer_question_detailed(_FakeCollection(0.9), "q")["generation_calls"] == 0


def test_api_maps_daily_quota_to_503_with_reset_time(api_client, monkeypatch):
    api_main, client = api_client

    def out_of_quota(*a, **k):
        raise rp.GeminiQuotaExhaustedError("quota used up", retry_after_s=48341.2)
    monkeypatch.setattr(api_main, "answer_question_detailed", out_of_quota)
    r = client.post("/ask", json={"question": "Is physio covered?"})
    assert r.status_code == 503 and r.headers["Retry-After"] == "48342"
    assert "quota" in r.json()["detail"]


def test_eval_stops_on_daily_quota_and_resumes_from_cache():
    calls = []

    def fn(q):
        calls.append(q)
        if len(calls) == 2:
            raise rp.GeminiQuotaExhaustedError("quota used up", retry_after_s=100.0)
        return _answer_fn(q)

    cache, kw = {}, dict(sleep_between=0, log=lambda _: None)
    with pytest.raises(ev.EvalIncomplete) as err:
        ev.run_eval(PAGED_QSET, fn, "idx", cache=cache, **kw)
    stop = err.value
    assert len(calls) == 2  # stopped asking after the quota error
    assert (stop.done, stop.total, stop.new) == (1, 3, 1)
    assert stop.skipped_ids == ["in_02", "out_01"] and stop.retry_after_s == 100.0
    assert "1/3 questions" in stop.message() and len(cache) == 1

    _, s = ev.run_eval(PAGED_QSET, fn, "idx", cache=cache, **kw)  # quota is back
    assert len(calls) == 4 and s["n_items"] == 3  # only the 2 missing ones re-asked


def test_eval_max_calls_budget_still_scores_cached_answers():
    calls = []
    fn = lambda q: (calls.append(q), _answer_fn(q))[1]  # noqa: E731
    cache, kw = {}, dict(sleep_between=0, log=lambda _: None)
    only_out = {**PAGED_QSET, "in_scope": []}
    ev.run_eval(only_out, fn, "idx", cache=cache, **kw)  # out_01 now cached
    calls.clear()

    with pytest.raises(ev.EvalIncomplete) as err:
        ev.run_eval(PAGED_QSET, fn, "idx", cache=cache, max_calls=1, **kw)
    stop = err.value
    assert calls == ["Is physio covered?"]  # in_01 cost the one allowed call
    assert stop.skipped_ids == ["in_02"] and stop.done == 2 and stop.calls == 1
    assert "--max-calls 1" in stop.reason


# --- pinned generator model (PLAN.md D15) ------------------------------------------
def test_default_generator_model_is_pinned():
    import re

    src = (REPO_ROOT / "src" / "rag_pipeline.py").read_text(encoding="utf-8")
    default = re.search(r'"INSURANCE_RAG_GEN_MODEL", "([^"]+)"', src).group(1)
    assert not rp.is_moving_alias(default), "pin the generator: no '-latest' alias"


def test_cached_answers_expire_only_for_a_moving_alias():
    assert rp.is_moving_alias("gemini-flash-latest") and not rp.is_moving_alias("gemini-3.8-flash")
    assert ev.default_max_age_days("gemini-3.8-flash") is None
    assert ev.default_max_age_days("gemini-flash-latest") == ev.DEFAULT_MAX_AGE_DAYS


def test_health_reports_the_configured_model(api_client):
    _, client = api_client
    assert client.get("/health").json()["model_default"] == rp.GEN_MODEL
