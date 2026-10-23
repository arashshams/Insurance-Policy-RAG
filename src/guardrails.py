"""
guardrails.py — cost / abuse controls shared by the Streamlit app and the API.

Framework-free (no Streamlit or FastAPI imports) so it is unit-testable offline.

* RateLimiter          sliding-window limiter keyed by any string (client IP,
                       session id, or a single "global" key).
* UploadIndexRegistry  process-wide registry of user-uploaded, in-memory
                       Chroma collections. Frees collections that have been
                       idle longer than a TTL (abandoned sessions) and caps
                       how many may exist at once.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Callable


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# --- Rate limits (all env-overridable; 0 disables a limit) -------------------
API_RATE_PER_CLIENT = _env_int("INSURANCE_RAG_API_RATE_PER_CLIENT", 10)   # per minute
API_RATE_GLOBAL = _env_int("INSURANCE_RAG_API_RATE_GLOBAL", 60)           # per minute
APP_QUESTIONS_PER_SESSION = _env_int("INSURANCE_RAG_APP_Q_PER_SESSION", 10)  # per minute
APP_QUESTIONS_GLOBAL = _env_int("INSURANCE_RAG_APP_Q_GLOBAL", 60)            # per minute
APP_UPLOADS_PER_SESSION = _env_int("INSURANCE_RAG_APP_UPLOADS_PER_SESSION", 3)  # per hour
APP_UPLOADS_GLOBAL = _env_int("INSURANCE_RAG_APP_UPLOADS_GLOBAL", 30)           # per hour

# --- Upload index lifetime ---------------------------------------------------
UPLOAD_TTL_SECONDS = _env_int("INSURANCE_RAG_UPLOAD_TTL_MIN", 30) * 60
MAX_UPLOAD_INDEXES = _env_int("INSURANCE_RAG_MAX_UPLOAD_INDEXES", 20)


class RateLimiter:
    """Thread-safe sliding-window rate limiter.

    allow(key) records a call and returns (True, 0.0) if it fits within
    `max_calls` per `window_s` seconds for that key, else (False, retry_after)
    without recording it. max_calls <= 0 disables the limit.
    """

    def __init__(self, max_calls: int, window_s: float,
                 clock: Callable[[], float] = time.monotonic):
        self.max_calls = max_calls
        self.window_s = window_s
        self._clock = clock
        self._calls: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str = "global") -> tuple[bool, float]:
        if self.max_calls <= 0:
            return True, 0.0
        now = self._clock()
        with self._lock:
            q = self._calls.setdefault(key, deque())
            while q and now - q[0] >= self.window_s:
                q.popleft()
            if len(q) >= self.max_calls:
                return False, max(0.0, self.window_s - (now - q[0]))
            q.append(now)
            # keep memory bounded: forget keys with no recent calls
            if len(self._calls) > 10_000:
                for k in [k for k, v in self._calls.items() if not v]:
                    del self._calls[k]
            return True, 0.0


class UploadIndexRegistry:
    """Tracks every live upload collection in the process.

    Streamlit gives no reliable "session ended" hook, so an abandoned
    session's in-memory index would otherwise live until the process restarts.
    Instead, every access touches the entry, and sweep() (called on every app
    run) drops collections idle for longer than `ttl_s`. `max_entries` caps
    concurrent uploads so memory and embedding spend stay bounded.

    `dropper(collection)` frees a collection (rag_pipeline.drop_collection).
    """

    def __init__(self, dropper: Callable[[Any], None],
                 ttl_s: float = UPLOAD_TTL_SECONDS,
                 max_entries: int = MAX_UPLOAD_INDEXES,
                 clock: Callable[[], float] = time.monotonic):
        self._drop = dropper
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._clock = clock
        self._entries: dict[str, dict] = {}   # name -> {"collection", "last_used"}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def has_capacity(self) -> bool:
        self.sweep()
        with self._lock:
            return self.max_entries <= 0 or len(self._entries) < self.max_entries

    def add(self, collection) -> str:
        name = collection.name
        with self._lock:
            self._entries[name] = {"collection": collection, "last_used": self._clock()}
        return name

    def get(self, name: str | None):
        """Return the live collection for `name` (refreshing its idle timer),
        or None if it was never registered or has been swept."""
        if not name:
            return None
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                return None
            entry["last_used"] = self._clock()
            return entry["collection"]

    def remove(self, name: str | None) -> None:
        if not name:
            return
        with self._lock:
            entry = self._entries.pop(name, None)
        if entry is not None:
            self._drop(entry["collection"])

    def sweep(self) -> list[str]:
        """Drop every collection idle longer than the TTL; return their names."""
        now = self._clock()
        with self._lock:
            stale = [n for n, e in self._entries.items()
                     if now - e["last_used"] > self.ttl_s]
            dropped = [self._entries.pop(n) for n in stale]
        for e in dropped:
            self._drop(e["collection"])
        return stale
