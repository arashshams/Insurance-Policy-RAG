"""
monitoring.py — privacy-safe request metrics for the API (PLAN.md M5, D20).

One small record per question to the API, holding only numbers and labels:
timings, whether the system said "I don't know" (and which layer), retrieval
distance, model and fallback, error type, pipeline fingerprint and app
version. NEVER the question, the answer, the passages or the client address.
Upload mode runs inside the Streamlit app and records nothing.

Storage is pluggable (INSURANCE_RAG_METRICS):
  firestore  Cloud Run: the project's (default) Firestore database, Native mode
  memory     local runs and tests (lost on restart)
  off        record nothing
Recording is best-effort: a slow or failing store never fails a request.
Records older than RETENTION_DAYS are deleted by the API itself (Firestore's
TTL feature is billed; plain deletes are inside the free quota).

summarize() turns records into the aggregates GET /stats returns and the
Streamlit "Monitoring" page charts: totals and per-day series only.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import threading
import time
from statistics import median
from typing import Any, Iterable

log = logging.getLogger("insurance_rag.monitoring")

BACKEND = os.environ.get("INSURANCE_RAG_METRICS", "memory").strip().lower()
COLLECTION = os.environ.get("INSURANCE_RAG_METRICS_COLLECTION", "api_requests")
RETENTION_DAYS = int(os.environ.get("INSURANCE_RAG_METRICS_RETENTION_DAYS", "90"))
WRITE_TIMEOUT_S = float(os.environ.get("INSURANCE_RAG_METRICS_TIMEOUT", "2"))

# The only fields a record may hold. Anything else passed in is dropped, so a
# future change can't start storing question text by accident.
FIELDS = (
    "ts", "day", "rid", "status", "seconds", "retrieve_s", "generate_s",
    "abstained", "abstention_layer", "nearest_distance", "n_retrieved",
    "model", "fallback_used", "fallback_reason", "generation_calls",
    "error", "pipeline", "version",
)


def _day(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).date().isoformat()


def build_event(*, rid: str, status: int, seconds: float, result: dict | None = None,
                error: str | None = None, pipeline: str | None = None,
                version: str | None = None, now: float | None = None) -> dict:
    """One metrics record from an /ask outcome (result is the pipeline's
    answer_question_detailed() dict, or None when it raised)."""
    ts = time.time() if now is None else now
    r = result or {}
    timings = r.get("timings") or {}
    abstained = r.get("abstained") if result is not None else None
    layer = None
    if abstained:
        layer = "threshold" if not r.get("retrieved") else "model"
    event = {
        "ts": ts, "day": _day(ts), "rid": rid, "status": int(status),
        "seconds": round(float(seconds), 3),
        "retrieve_s": timings.get("retrieve_s"), "generate_s": timings.get("generate_s"),
        "abstained": abstained, "abstention_layer": layer,
        "nearest_distance": r.get("nearest_distance"),
        "n_retrieved": len(r.get("retrieved") or []) if result is not None else None,
        "model": r.get("model_used"),
        "fallback_used": bool(r.get("fallback_used")) if result is not None else None,
        "fallback_reason": r.get("fallback_reason"),
        "generation_calls": r.get("generation_calls"),
        "error": error, "pipeline": pipeline, "version": version,
    }
    return {k: event[k] for k in FIELDS}


# --- stores -----------------------------------------------------------------------
class MemoryStore:
    """In-process store for local runs and tests."""

    def __init__(self):
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def record(self, event: dict) -> None:
        with self._lock:
            self._events.append({k: event.get(k) for k in FIELDS})

    def events_since(self, ts: float) -> list[dict]:
        with self._lock:
            return [e for e in self._events if e["ts"] >= ts]

    def prune(self, before_ts: float) -> int:
        with self._lock:
            keep = [e for e in self._events if e["ts"] >= before_ts]
            removed = len(self._events) - len(keep)
            self._events = keep
            return removed


class FirestoreStore:
    """The project's (default) Firestore database (free tier: 1 GiB, 20k
    writes and 50k reads per day). Uses the Cloud Run service account's
    credentials automatically; it needs roles/datastore.user."""

    def __init__(self, collection: str = COLLECTION, client=None):
        self._collection_name = collection
        self._client = client

    def _collection(self):
        if self._client is None:
            from google.cloud import firestore  # only needed on Cloud Run

            self._client = firestore.Client()
        return self._client.collection(self._collection_name)

    def record(self, event: dict) -> None:
        self._collection().document(event["rid"]).set(
            {k: event.get(k) for k in FIELDS}, timeout=WRITE_TIMEOUT_S)

    def events_since(self, ts: float) -> list[dict]:
        query = self._collection().where("ts", ">=", ts)
        return [doc.to_dict() for doc in query.stream(timeout=20)]

    def prune(self, before_ts: float, batch_size: int = 200) -> int:
        old = self._collection().where("ts", "<", before_ts).limit(batch_size)
        removed = 0
        for doc in old.stream(timeout=20):
            doc.reference.delete(timeout=WRITE_TIMEOUT_S)
            removed += 1
        return removed


_store = None
_store_lock = threading.Lock()


def get_store():
    """The configured store (one per process), or None when metrics are off."""
    global _store
    if BACKEND in ("off", "none", ""):
        return None
    with _store_lock:
        if _store is None:
            _store = FirestoreStore() if BACKEND == "firestore" else MemoryStore()
        return _store


def record(event: dict, store=None) -> bool:
    """Best-effort write: never raises. Returns whether it was stored."""
    store = store if store is not None else get_store()
    if store is None:
        return False
    try:
        store.record(event)
        return True
    except Exception as exc:  # noqa: BLE001 - metrics must never break a request
        log.warning("metrics write failed: %s", type(exc).__name__)
        return False


_last_prune = 0.0


def prune_old(store=None, now: float | None = None, every_s: float = 86400) -> int:
    """Delete records older than RETENTION_DAYS, at most once a day per
    process (called from /stats, so the request path stays light)."""
    global _last_prune
    store = store if store is not None else get_store()
    now = time.time() if now is None else now
    if store is None or now - _last_prune < every_s:
        return 0
    _last_prune = now
    try:
        return store.prune(now - RETENTION_DAYS * 86400)
    except Exception as exc:  # noqa: BLE001
        log.warning("metrics prune failed: %s", type(exc).__name__)
        return 0


# --- aggregation ---------------------------------------------------------------------
def _pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    vals = sorted(values)
    idx = min(len(vals) - 1, max(0, round(q * (len(vals) - 1))))
    return round(vals[idx], 3)


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _group(events: list[dict]) -> dict[str, Any]:
    ok = [e for e in events if e.get("status") == 200]
    abstained = [e for e in ok if e.get("abstained")]
    seconds = [e["seconds"] for e in ok if e.get("seconds") is not None]
    dist = [e["nearest_distance"] for e in ok if e.get("nearest_distance") is not None]
    return {
        "requests": len(events),
        "answered_ok": len(ok),
        "errors": len(events) - len(ok),
        "error_rate": _rate(len(events) - len(ok), len(events)),
        "idk_rate": _rate(len(abstained), len(ok)),
        "idk_by_threshold": sum(e.get("abstention_layer") == "threshold" for e in abstained),
        "idk_by_model": sum(e.get("abstention_layer") == "model" for e in abstained),
        "fallback_rate": _rate(sum(bool(e.get("fallback_used")) for e in ok), len(ok)),
        "latency_p50_s": _pct(seconds, 0.5),
        "latency_p95_s": _pct(seconds, 0.95),
        "nearest_distance_median": round(median(dist), 4) if dist else None,
    }


def summarize(events: Iterable[dict], days: int, now: float | None = None,
              threshold: float | None = None) -> dict[str, Any]:
    """Aggregates for the last `days` days: overall, per UTC day (every day in
    the window, zeros included), and error types. No individual records."""
    now = time.time() if now is None else now
    since = now - days * 86400
    events = [e for e in events if e.get("ts", 0) >= since]
    first = _dt.datetime.fromtimestamp(since, _dt.timezone.utc).date()
    last = _dt.datetime.fromtimestamp(now, _dt.timezone.utc).date()
    day_list = [(first + _dt.timedelta(d)).isoformat()
                for d in range((last - first).days + 1)]
    errors: dict[str, int] = {}
    for e in events:
        if e.get("error"):
            errors[e["error"]] = errors.get(e["error"], 0) + 1
    models: dict[str, int] = {}
    for e in events:
        if e.get("model"):
            models[e["model"]] = models.get(e["model"], 0) + 1
    return {
        "days": days,
        "since": _dt.datetime.fromtimestamp(since, _dt.timezone.utc).isoformat(),
        "threshold": threshold,
        "overall": _group(events),
        "by_day": [{"day": d, **_group([e for e in events if e.get("day") == d])}
                   for d in day_list],
        "errors": dict(sorted(errors.items(), key=lambda kv: -kv[1])),
        "models": models,
    }
