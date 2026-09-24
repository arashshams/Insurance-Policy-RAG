"""
evaluate.py — evaluation harness for Insurance-Policy-RAG.

Runs the question set in notebooks/eval/eval_questions.json against the SAME
pipeline code the app and API ship (src/rag_pipeline.py), on any Chroma
index — by default the bundled demo index at app/demo_index/, i.e. exactly
what production serves.

Metrics (deterministic, no LLM judge):
  * out-of-scope abstention rate  (guardrail: must answer "I don't know")
  * in-scope retrieval hit rate   (>=1 chunk passed the distance threshold)
  * in-scope answer-keyword rate  (all expected_keywords appear in the answer)
  * in-scope wrongful abstentions (listed by id)

Free-tier safe: sequential, paced, and cached. The cache key includes the
question text, index path, model and threshold, so rewording a question or
switching index/model re-runs that question instead of reusing a stale result.

Run from the repo root (needs GEMINI_API_KEY):
    python -m src.evaluate                      # demo index, default cache
    python -m src.evaluate --index path/to/chroma --no-cache
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import rag_pipeline as rp  # noqa: E402

DEFAULT_QUESTIONS = REPO_ROOT / "notebooks" / "eval" / "eval_questions.json"
DEFAULT_RESULTS = REPO_ROOT / "notebooks" / "eval" / "eval_results.json"
DEFAULT_INDEX = REPO_ROOT / "app" / "demo_index"


# --- scoring helpers ---------------------------------------------------------
def contains_keywords(answer: str, keywords: list[str]) -> bool | None:
    """True if every expected keyword appears in the answer (case-insensitive).
    None if no real keywords are set yet (still the "TODO" placeholder)."""
    kws = [k for k in keywords if k and k != "TODO"]
    if not kws:
        return None
    a = answer.lower()
    return all(k.lower() in a for k in kws)


def is_abstention(answer: str, idk: str = rp.IDK_ANSWER) -> bool:
    """True if the answer is the IDK abstention (tolerant of punctuation/space)."""
    norm = lambda s: s.strip().rstrip(".").lower()  # noqa: E731
    return norm(answer) == norm(idk)


def _cache_key(q: dict, index_label: str) -> str:
    raw = "|".join([
        q["id"], q["question"], index_label, rp.GEN_MODEL, rp.EMBED_MODEL,
        str(rp.DISTANCE_THRESHOLD), str(rp.K_DEFAULT),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --- core --------------------------------------------------------------------
def run_eval(
    qset: dict,
    answer_fn: Callable[[str], tuple[str, list, list]],
    index_label: str,
    cache: dict | None = None,
    save_cache: Callable[[dict], None] | None = None,
    sleep_between: float = 2.0,
    log: Callable[[str], None] = print,
) -> tuple[list[dict], dict]:
    """Run every question through answer_fn and return (records, summary).

    answer_fn(question) -> (answer, pages, retrieved), i.e. answer_question
    with the collection already bound. Kept injectable so the harness itself
    can be unit-tested without an API key.
    """
    cache = {} if cache is None else cache
    idk = qset.get("idk_answer", rp.IDK_ANSWER)
    records: list[dict] = []

    for category in ("in_scope", "out_of_scope"):
        for q in qset[category]:
            key = _cache_key(q, index_label)
            if key in cache:
                rec = cache[key]
            else:
                answer, pages, retrieved = answer_fn(q["question"])
                rec = {
                    "id": q["id"], "category": category, "question": q["question"],
                    "answer": answer, "pages": pages,
                    "n_retrieved": len(retrieved),
                    "top_distance": min(
                        (r["score"] for r in retrieved if r.get("score") is not None),
                        default=None,
                    ),
                    "abstained": is_abstention(answer, idk),
                    "index": index_label, "model": rp.GEN_MODEL,
                }
                if category == "in_scope":
                    rec["keyword_pass"] = contains_keywords(
                        answer, q.get("expected_keywords", [])
                    )
                cache[key] = rec
                if save_cache:
                    save_cache(cache)  # incremental: a crash never loses progress
                if sleep_between:
                    time.sleep(sleep_between)
            records.append(rec)
            if category == "in_scope":
                log(f"IN  {rec['id']}: retrieved={rec['n_retrieved']} "
                    f"abstained={rec['abstained']} keyword_pass={rec.get('keyword_pass')}")
            else:
                log(f"OUT {rec['id']}: abstained={rec['abstained']}")

    return records, summarize(records)


def summarize(records: list[dict]) -> dict:
    ins = [r for r in records if r["category"] == "in_scope"]
    outs = [r for r in records if r["category"] == "out_of_scope"]
    calibrated = [r for r in ins if r.get("keyword_pass") is not None]
    rate = lambda n, d: (n / d) if d else None  # noqa: E731
    return {
        "n_in_scope": len(ins),
        "n_out_of_scope": len(outs),
        "out_of_scope_abstention_rate": rate(sum(r["abstained"] for r in outs), len(outs)),
        "in_scope_retrieval_hit_rate": rate(sum(r["n_retrieved"] > 0 for r in ins), len(ins)),
        "in_scope_answered": sum(not r["abstained"] for r in ins),
        "in_scope_keyword_rate": rate(sum(r["keyword_pass"] for r in calibrated), len(calibrated)),
        "in_scope_abstained_ids": [r["id"] for r in ins if r["abstained"]],
        "in_scope_keyword_fail_ids": [r["id"] for r in calibrated if not r["keyword_pass"]],
    }


def format_summary(s: dict, index_label: str) -> str:
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"  # noqa: E731
    lines = [
        f"=== Evaluation summary (index: {index_label}, model: {rp.GEN_MODEL}) ===",
        f"Out-of-scope abstention rate : {pct(s['out_of_scope_abstention_rate'])}  (target 100%)",
        f"In-scope retrieval hit rate  : {pct(s['in_scope_retrieval_hit_rate'])}  (target ~100%)",
        f"In-scope answered            : {s['in_scope_answered']}/{s['n_in_scope']}",
        f"In-scope answer-keyword rate : {pct(s['in_scope_keyword_rate'])}",
    ]
    if s["in_scope_abstained_ids"]:
        lines.append(f"In-scope questions that abstained: {s['in_scope_abstained_ids']}")
    if s["in_scope_keyword_fail_ids"]:
        lines.append(f"In-scope keyword misses: {s['in_scope_keyword_fail_ids']}")
    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--index", default=str(DEFAULT_INDEX),
                    help="Chroma persist dir to evaluate (default: app/demo_index)")
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    ap.add_argument("--results", default=str(DEFAULT_RESULTS))
    ap.add_argument("--no-cache", action="store_true", help="ignore cached results")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between API calls")
    args = ap.parse_args(argv)

    try:
        rp._read_api_key()  # fail fast, before opening anything
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    qset = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    collection = rp.load_persistent_collection(persist_dir=args.index)
    try:
        index_label = str(Path(args.index).resolve().relative_to(REPO_ROOT))
    except ValueError:
        index_label = str(Path(args.index).resolve())
    print(f"Index: {index_label} ({collection.count()} chunks)")

    results_path = Path(args.results)
    cache = {}
    if not args.no_cache and results_path.exists():
        cache = json.loads(results_path.read_text(encoding="utf-8"))

    def _save(c):
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")

    _records, summary = run_eval(
        qset,
        answer_fn=lambda q: rp.answer_question(collection, q),
        index_label=index_label,
        cache=cache,
        save_cache=_save,
        sleep_between=args.sleep,
    )
    print()
    print(format_summary(summary, index_label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
