"""
Offline tests for privacy-safe monitoring (src/monitoring.py, the API's
/stats endpoint and metrics recording, the app's stats client). PLAN.md M5.
No Firestore, network or API key needed: stores are in-memory or faked.
"""

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import monitoring as mon  # noqa: E402

DAY = 86400
NOW = 1_800_000_000.0  # a fixed "now" (2027-01-15 UTC)
QUESTION = "Is my private medical condition covered?"
ANSWER = "Yes, your condition is covered on page 7."


def _result(abstained=False, retrieved=1, fallback=False, distance=0.31):
    return {
        "answer": "I don't know" if abstained else ANSWER, "pages": [] if abstained else [7],
        "retrieved": [{"id": "doc_1", "text": "policy text about " + QUESTION,
                       "metadata": {"page": 7}, "score": distance}] * retrieved,
        "abstained": abstained, "nearest_distance": distance,
        "model_used": "gemini-3.6-flash" if fallback else "gemini-3.8-flash",
        "fallback_used": fallback, "fallback_reason": "InternalServerError" if fallback else None,
        "generation_calls": 0 if (abstained and not retrieved) else 1,
        "timings": {"retrieve_s": 0.4, "generate_s": 1.2},
        "question": QUESTION,  # never stored, even if a caller passes it along
    }


# --- records ------------------------------------------------------------------------
def test_event_holds_only_numbers_and_labels():
    e = mon.build_event(rid="r1", status=200, seconds=1.234, result=_result(),
                        pipeline="abc", version="rev-1", now=NOW)
    assert list(e) == list(mon.FIELDS)
    text = json.dumps(e)
    assert QUESTION not in text and ANSWER not in text and "policy text" not in text
    assert e["day"] == "2027-01-15" and e["seconds"] == 1.234 and e["n_retrieved"] == 1
    assert e["retrieve_s"] == 0.4 and e["generate_s"] == 1.2
    assert e["abstained"] is False and e["abstention_layer"] is None


def test_event_names_the_abstention_layer_and_errors():
    by_threshold = mon.build_event(rid="a", status=200, seconds=0.5,
                                   result=_result(abstained=True, retrieved=0), now=NOW)
    by_model = mon.build_event(rid="b", status=200, seconds=2,
                               result=_result(abstained=True, retrieved=2), now=NOW)
    failed = mon.build_event(rid="c", status=503, seconds=23, error="GeminiUnavailableError",
                             now=NOW)
    assert by_threshold["abstention_layer"] == "threshold"
    assert by_model["abstention_layer"] == "model"
    assert failed["error"] == "GeminiUnavailableError" and failed["abstained"] is None
    assert failed["n_retrieved"] is None and failed["fallback_used"] is None


def test_recording_is_best_effort():
    class Broken:
        def record(self, event):
            raise RuntimeError("store down")
    event = mon.build_event(rid="r", status=200, seconds=1, now=NOW)
    assert mon.record(event, store=Broken()) is False  # no exception
    store = mon.MemoryStore()
    assert mon.record(event, store=store) is True and store.events_since(0)[0]["rid"] == "r"


def test_memory_store_prunes_and_pruning_runs_once_a_day(monkeypatch):
    store = mon.MemoryStore()
    for age_days in (1, 89, 91, 200):
        store.record(mon.build_event(rid=str(age_days), status=200, seconds=1,
                                     now=NOW - age_days * DAY))
    monkeypatch.setattr(mon, "_last_prune", 0.0)
    assert mon.prune_old(store, now=NOW) == 2  # older than 90 days
    assert sorted(e["rid"] for e in store.events_since(0)) == ["1", "89"]
    assert mon.prune_old(store, now=NOW + 60) == 0  # not again the same day


# --- aggregation ------------------------------------------------------------------------------
def _events():
    ev = []
    ev.append(mon.build_event(rid="1", status=200, seconds=2.0, result=_result(), now=NOW - 3600))
    ev.append(mon.build_event(rid="2", status=200, seconds=4.0,
                              result=_result(abstained=True, retrieved=0, distance=0.45),
                              now=NOW - 7200))
    ev.append(mon.build_event(rid="3", status=200, seconds=6.0, result=_result(fallback=True),
                              now=NOW - 2 * DAY))
    ev.append(mon.build_event(rid="4", status=503, seconds=23.0, error="GeminiUnavailableError",
                              now=NOW - 2 * DAY))
    ev.append(mon.build_event(rid="old", status=200, seconds=1.0, result=_result(),
                              now=NOW - 30 * DAY))  # outside a 7-day window
    return ev


def test_summary_overall_numbers():
    s = mon.summarize(_events(), days=7, now=NOW, threshold=0.37)
    o = s["overall"]
    assert (o["requests"], o["answered_ok"], o["errors"]) == (4, 3, 1)
    assert o["error_rate"] == 0.25 and o["idk_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert (o["idk_by_threshold"], o["idk_by_model"]) == (1, 0)
    assert o["fallback_rate"] == pytest.approx(1 / 3, abs=1e-4)
    assert o["latency_p50_s"] == 4.0 and o["latency_p95_s"] == 6.0
    assert o["nearest_distance_median"] == 0.31
    assert s["errors"] == {"GeminiUnavailableError": 1}
    assert s["models"] == {"gemini-3.8-flash": 2, "gemini-3.6-flash": 1}
    assert s["threshold"] == 0.37


def test_summary_has_every_day_in_the_window_with_zeros():
    s = mon.summarize(_events(), days=7, now=NOW)
    days = [d["day"] for d in s["by_day"]]
    assert len(days) == 8 and days[-1] == "2027-01-15"  # window spans 8 calendar days
    quiet = next(d for d in s["by_day"] if d["day"] == "2027-01-10")
    assert quiet["requests"] == 0 and quiet["idk_rate"] is None
    today = next(d for d in s["by_day"] if d["day"] == "2027-01-15")
    assert today["requests"] == 2


def test_empty_summary():
    s = mon.summarize([], days=7, now=NOW)
    assert s["overall"]["requests"] == 0 and s["overall"]["latency_p50_s"] is None


# --- Firestore store (faked client) ------------------------------------------------------------
class _FakeDoc:
    def __init__(self, data, store):
        self._data, self._store = data, store
        self.reference = SimpleNamespace(delete=lambda timeout=None: store.deleted.append(data["rid"]))

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, store, op, value, limit=None):
        self.store, self.op, self.value, self._limit = store, op, value, limit

    def limit(self, n):
        return _FakeQuery(self.store, self.op, self.value, n)

    def stream(self, timeout=None):
        match = [d for d in self.store.docs.values()
                 if (d["ts"] >= self.value if self.op == ">=" else d["ts"] < self.value)]
        return [_FakeDoc(d, self.store) for d in match[: self._limit or None]]


class _FakeCollection:
    def __init__(self):
        self.docs, self.deleted, self.timeouts = {}, [], []

    def document(self, rid):
        def set_(data, timeout=None):
            self.timeouts.append(timeout)
            self.docs[rid] = data
        return SimpleNamespace(set=set_)

    def where(self, field, op, value):
        assert field == "ts"
        return _FakeQuery(self, op, value)


def test_firestore_store_writes_only_whitelisted_fields_with_a_timeout():
    coll = _FakeCollection()
    store = mon.FirestoreStore(client=SimpleNamespace(collection=lambda name: coll))
    event = {**mon.build_event(rid="r1", status=200, seconds=1, result=_result(), now=NOW),
             "question": QUESTION}
    store.record(event)
    assert set(coll.docs["r1"]) == set(mon.FIELDS) and coll.timeouts == [mon.WRITE_TIMEOUT_S]
    store.record(mon.build_event(rid="r2", status=200, seconds=1, now=NOW - 100 * DAY))
    assert [e["rid"] for e in store.events_since(NOW - DAY)] == ["r1"]
    assert store.prune(NOW - 90 * DAY) == 1 and coll.deleted == ["r2"]


# --- API: recording and /stats ------------------------------------------------------------------
@pytest.fixture
def api(monkeypatch):
    pytest.importorskip("fastapi.testclient")
    from api import main as api_main
    from src import guardrails as gr

    store = mon.MemoryStore()
    monkeypatch.setattr(mon, "get_store", lambda: store)
    monkeypatch.setattr(mon, "_last_prune", 0.0)
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.delenv("INSURANCE_RAG_API_TOKEN", raising=False)
    monkeypatch.setattr(api_main, "_get_collection", lambda: object())
    monkeypatch.setattr(api_main, "_client_limiter", gr.RateLimiter(100, 60))
    monkeypatch.setattr(api_main, "_global_limiter", gr.RateLimiter(100, 60))
    api_main._test_store = store
    return api_main


def test_ask_stores_one_record_without_the_question(api, monkeypatch):
    from fastapi.testclient import TestClient

    from src import rag_pipeline as rp

    monkeypatch.setattr(api, "answer_question_detailed", lambda *a, **k: _result())
    client = TestClient(api.app)
    assert client.post("/ask", json={"question": QUESTION}).status_code == 200

    def down(*a, **k):
        raise rp.GeminiUnavailableError("Gemini is temporarily unavailable")
    monkeypatch.setattr(api, "answer_question_detailed", down)
    assert client.post("/ask", json={"question": QUESTION}).status_code == 503

    events = api._test_store.events_since(0)
    assert [e["status"] for e in events] == [200, 503]
    assert events[1]["error"] == "GeminiUnavailableError"
    assert events[0]["pipeline"] == api._PIPELINE and events[0]["version"] == api.APP_VERSION
    assert QUESTION not in json.dumps(events) and ANSWER not in json.dumps(events)


def test_a_broken_store_never_breaks_ask(api, monkeypatch):
    from fastapi.testclient import TestClient

    class Broken:
        def record(self, event):
            raise RuntimeError("firestore down")
    monkeypatch.setattr(mon, "get_store", lambda: Broken())
    monkeypatch.setattr(api, "answer_question_detailed", lambda *a, **k: _result())
    assert TestClient(api.app).post("/ask", json={"question": "q"}).status_code == 200


def test_stats_returns_aggregates_only(api, monkeypatch):
    from fastapi.testclient import TestClient

    for e in _events():
        api._test_store.record({**e, "ts": e["ts"] - NOW + time.time()})
    r = TestClient(api.app).get("/stats", params={"days": 7})
    assert r.status_code == 200
    body = r.json()
    assert body["overall"]["requests"] == 4 and len(body["by_day"]) >= 7
    assert "rid" not in json.dumps(body["by_day"])  # no individual records
    assert body["backend"] == mon.BACKEND and body["threshold"] == api.DISTANCE_THRESHOLD


def test_stats_needs_the_token_and_validates_days(api, monkeypatch):
    from fastapi.testclient import TestClient

    client = TestClient(api.app)
    assert client.get("/stats", params={"days": 0}).status_code == 422
    assert client.get("/stats", params={"days": 91}).status_code == 422
    monkeypatch.setenv("INSURANCE_RAG_API_TOKEN", "secret")
    assert client.get("/stats").status_code == 401
    assert client.get("/stats", headers={"Authorization": "Bearer secret"}).status_code == 200


def test_stats_when_monitoring_is_off_or_the_store_is_down(api, monkeypatch):
    from fastapi.testclient import TestClient

    client = TestClient(api.app)
    monkeypatch.setattr(mon, "get_store", lambda: None)
    assert client.get("/stats").status_code == 404

    class Down:
        def events_since(self, ts):
            raise RuntimeError("firestore down")

        def prune(self, before):
            return 0
    monkeypatch.setattr(mon, "get_store", lambda: Down())
    r = client.get("/stats")
    assert r.status_code == 503 and "unavailable" in r.json()["detail"]


# --- the app's stats client ------------------------------------------------------------------------
@pytest.fixture(scope="module")
def api_client():
    pytest.importorskip("requests")
    spec = importlib.util.spec_from_file_location("api_client", REPO_ROOT / "app" / "api_client.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def test_stats_client(api_client):
    calls = []

    def get(url, params, headers, timeout):
        calls.append((url, params, headers))
        return _Resp(200, {"overall": {"requests": 3}})
    assert api_client.stats("https://api.example/", days=30, token="t", get=get)[
        "overall"]["requests"] == 3
    assert calls == [("https://api.example/stats", {"days": 30}, {"Authorization": "Bearer t"})]
    with pytest.raises(api_client.ApiError, match="turned off"):
        api_client.stats("https://api.example", get=lambda *a, **k: _Resp(
            404, {"detail": "Monitoring is turned off on this server."}))
