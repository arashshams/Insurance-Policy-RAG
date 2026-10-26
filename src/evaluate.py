"""
evaluate.py — evaluation harness for Insurance-Policy-RAG.

Runs the question set in notebooks/eval/eval_questions.json against the SAME
pipeline code the app and API ship (src/rag_pipeline.py), on any Chroma
index — by default the bundled demo index at app/demo_index/, i.e. exactly
what production serves — or on a PDF of your own (--pdf), to calibrate it.

Metrics (deterministic, no LLM judge):
  * out-of-scope abstention rate   (guardrail: must answer "I don't know")
  * how each abstention happened   (distance threshold vs. the model refusing
                                    to answer from chunks that passed it)
  * in-scope retrieval hit rate   (>=1 chunk passed the distance threshold)
  * in-scope retrieval page rate   (an expected page was among those chunks)
  * in-scope citation page rate    (the answer cited a chunk on an expected page)
  * in-scope answer-keyword rate   (all expected_keywords appear in the answer)
  * in-scope wrongful abstentions  (listed by id)
  * distance margin                (largest in-scope vs smallest out-of-scope
                                    nearest-chunk distance, measured BEFORE the
                                    threshold) and a suggested threshold
Abstention uses rag_pipeline.is_abstention, the same definition as the app/API.

Free-tier safe: sequential, paced, and cached. The cache key includes the
question text, index path, model and threshold, so rewording a question or
switching index/model re-runs that question instead of reusing a stale result.
Scoring is re-applied to cached answers on every run, so editing a question's
expected_keywords or expected_pages takes effect without new API calls.
Because the default model is a moving alias ("gemini-flash-latest") and
Gemini's OpenAI-compatible endpoint doesn't report the version behind it,
cached results also expire after --max-age-days.

Run from the repo root (needs GEMINI_API_KEY):
    python -m src.evaluate                      # demo index, default cache
    python -m src.evaluate --index path/to/chroma --no-cache
    python -m src.evaluate --pdf my_policy.pdf --questions my_questions.json \
        --results my_results.json               # calibrate a new policy
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
DEFAULT_MAX_AGE_DAYS = 14.0


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
    """Shared abstention definition (delegates to the pipeline's)."""
    return rp.is_abstention(answer, idk)


def page_hit(pages, expected_pages) -> bool | None:
    """True if any expected page is in `pages`; None if none are specified."""
    if not expected_pages:
        return None
    return bool(set(pages or []) & set(expected_pages))


def _cache_key(q: dict, index_label: str) -> str:
    raw = "|".join([
        q["id"], q["question"], index_label, rp.GEN_MODEL, rp.EMBED_MODEL,
        str(rp.DISTANCE_THRESHOLD), str(rp.K_DEFAULT),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _normalize_result(out, idk: str) -> dict:
    """Accept either answer_question_detailed()'s dict or the legacy
    (answer, pages, retrieved) tuple, and return a dict with the fields the
    harness needs."""
    if isinstance(out, dict):
        return out
    answer, pages, retrieved = out
    scores = [r.get("score") for r in retrieved if r.get("score") is not None]
    return {
        "answer": answer, "pages": pages, "retrieved": retrieved,
        "abstained": is_abstention(answer, idk),
        "citations_verified": None, "cited_ids": [],
        "nearest_distance": min(scores) if scores else None,
        "model_resolved": None,
    }


def score_record(rec: dict, q: dict) -> dict:
    """(Re)compute the scoring fields of an in-scope record from the CURRENT
    question definition. Scoring is applied to cached records on every run,
    so editing expected_keywords / expected_pages takes effect without
    re-calling the API (the cache only stores what the pipeline returned)."""
    if rec["category"] != "in_scope":
        return rec
    expected_pages = q.get("expected_pages")
    rec["keyword_pass"] = contains_keywords(rec["answer"], q.get("expected_keywords", []))
    rec["retrieval_page_hit"] = page_hit(rec.get("retrieved_pages"), expected_pages)
    rec["citation_page_hit"] = (
        None if not expected_pages
        else (False if rec["abstained"] else page_hit(rec.get("pages"), expected_pages))
    )
    return rec


def _is_fresh(rec: dict, max_age_s: float | None, now: float) -> bool:
    if max_age_s is None:
        return True
    ts = rec.get("evaluated_at")
    return isinstance(ts, (int, float)) and now - ts <= max_age_s


# --- core --------------------------------------------------------------------
def run_eval(
    qset: dict,
    answer_fn: Callable[[str], object],
    index_label: str,
    cache: dict | None = None,
    save_cache: Callable[[dict], None] | None = None,
    sleep_between: float = 2.0,
    log: Callable[[str], None] = print,
    max_age_days: float | None = DEFAULT_MAX_AGE_DAYS,
    clock: Callable[[], float] = time.time,
) -> tuple[list[dict], dict]:
    """Run every question through answer_fn and return (records, summary).

    answer_fn(question) -> answer_question_detailed()-style dict (preferred)
    or the legacy (answer, pages, retrieved) tuple, with the collection
    already bound. Kept injectable so the harness itself can be unit-tested
    without an API key. Cached records older than max_age_days are re-run
    (None = never expire). Scoring (keywords, pages) is recomputed for cached
    records too, so edits to the question set's expectations always apply.
    """
    cache = {} if cache is None else cache
    idk = qset.get("idk_answer", rp.IDK_ANSWER)
    max_age_s = None if max_age_days is None else max_age_days * 86400
    records: list[dict] = []

    for category in ("in_scope", "out_of_scope"):
        for q in qset[category]:
            key = _cache_key(q, index_label)
            if key in cache and _is_fresh(cache[key], max_age_s, clock()):
                rec = score_record(cache[key], q)
            else:
                res = _normalize_result(answer_fn(q["question"]), idk)
                retrieved = res["retrieved"]
                retrieved_pages = sorted({
                    r.get("metadata", {}).get("page") for r in retrieved
                    if r.get("metadata", {}).get("page") is not None
                })
                rec = {
                    "id": q["id"], "category": category, "question": q["question"],
                    "answer": res["answer"], "pages": res["pages"],
                    "retrieved_pages": retrieved_pages,
                    "n_retrieved": len(retrieved),
                    # closest chunk BEFORE thresholding (calibration signal)
                    "nearest_distance": res.get("nearest_distance"),
                    # closest chunk that PASSED the threshold (legacy field)
                    "top_distance": min(
                        (r["score"] for r in retrieved if r.get("score") is not None),
                        default=None,
                    ),
                    "abstained": bool(res["abstained"]),
                    "citations_verified": res.get("citations_verified"),
                    "index": index_label, "model": rp.GEN_MODEL,
                    "model_resolved": res.get("model_resolved"),
                    "evaluated_at": clock(),
                }
                score_record(rec, q)
                cache[key] = rec
                if save_cache:
                    save_cache(cache)  # incremental: a crash never loses progress
                if sleep_between:
                    time.sleep(sleep_between)
            records.append(rec)
            dist = rec.get("nearest_distance")
            dist_s = "n/a" if dist is None else f"{dist:.3f}"
            if category == "in_scope":
                log(f"IN  {rec['id']}: nearest={dist_s} retrieved={rec['n_retrieved']} "
                    f"abstained={rec['abstained']} keyword_pass={rec.get('keyword_pass')} "
                    f"page_hit={rec.get('citation_page_hit')}")
            else:
                stopped_by = ("" if not rec["abstained"] else
                              " (threshold)" if rec["n_retrieved"] == 0 else " (model refused)")
                log(f"OUT {rec['id']}: nearest={dist_s} retrieved={rec['n_retrieved']} "
                    f"abstained={rec['abstained']}{stopped_by}")

    return records, summarize(records)


def suggest_threshold(records: list[dict]) -> dict:
    """From nearest (pre-threshold) distances, report the separation between
    in-scope and out-of-scope questions and a midpoint threshold if they are
    separable. Distances: lower = more similar."""
    ins = [r["nearest_distance"] for r in records
           if r["category"] == "in_scope" and r.get("nearest_distance") is not None]
    outs = [r["nearest_distance"] for r in records
            if r["category"] == "out_of_scope" and r.get("nearest_distance") is not None]
    if not ins or not outs:
        return {"in_scope_max": max(ins, default=None),
                "out_of_scope_min": min(outs, default=None),
                "separable": None, "suggested_threshold": None}
    hi_in, lo_out = max(ins), min(outs)
    separable = hi_in < lo_out
    return {
        "in_scope_max": hi_in,
        "out_of_scope_min": lo_out,
        "separable": separable,
        "suggested_threshold": round((hi_in + lo_out) / 2, 3) if separable else None,
    }


def summarize(records: list[dict]) -> dict:
    ins = [r for r in records if r["category"] == "in_scope"]
    outs = [r for r in records if r["category"] == "out_of_scope"]
    calibrated = [r for r in ins if r.get("keyword_pass") is not None]
    paged_retr = [r for r in ins if r.get("retrieval_page_hit") is not None]
    paged_cite = [r for r in ins if r.get("citation_page_hit") is not None]
    rate = lambda n, d: (n / d) if d else None  # noqa: E731
    models = sorted({r.get("model_resolved") for r in records if r.get("model_resolved")})
    return {
        "n_in_scope": len(ins),
        "n_out_of_scope": len(outs),
        "out_of_scope_abstention_rate": rate(sum(r["abstained"] for r in outs), len(outs)),
        "in_scope_retrieval_hit_rate": rate(sum(r["n_retrieved"] > 0 for r in ins), len(ins)),
        "in_scope_retrieval_page_rate": rate(
            sum(r["retrieval_page_hit"] for r in paged_retr), len(paged_retr)),
        "in_scope_citation_page_rate": rate(
            sum(r["citation_page_hit"] for r in paged_cite), len(paged_cite)),
        "in_scope_answered": sum(not r["abstained"] for r in ins),
        "in_scope_keyword_rate": rate(sum(r["keyword_pass"] for r in calibrated), len(calibrated)),
        "in_scope_abstained_ids": [r["id"] for r in ins if r["abstained"]],
        "in_scope_keyword_fail_ids": [r["id"] for r in calibrated if not r["keyword_pass"]],
        "in_scope_page_miss_ids": [r["id"] for r in paged_cite if not r["citation_page_hit"]],
        "out_of_scope_answered_ids": [r["id"] for r in outs if not r["abstained"]],
        # How each out-of-scope abstention happened: the distance threshold
        # (no chunks passed, no LLM call) or the model declining to answer
        # from chunks that did pass. Both are correct outcomes; the split
        # shows how much the guardrail depends on each layer.
        "out_of_scope_threshold_ids": [r["id"] for r in outs
                                       if r["abstained"] and r["n_retrieved"] == 0],
        "out_of_scope_model_refused_ids": [r["id"] for r in outs
                                           if r["abstained"] and r["n_retrieved"] > 0],
        "distance_margin": suggest_threshold(records),
        "models_resolved": models,
    }


def format_summary(s: dict, index_label: str) -> str:
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"  # noqa: E731
    num = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
    m = s["distance_margin"]
    resolved_list = s.get("models_resolved") or []
    if not resolved_list:
        resolved = "not reported"
    elif resolved_list == [rp.GEN_MODEL]:
        resolved = "exact version not reported by the API"
    else:
        resolved = ", ".join(resolved_list)
    lines = [
        f"=== Evaluation summary (index: {index_label}, model: {rp.GEN_MODEL} -> {resolved}) ===",
        f"Out-of-scope abstention rate : {pct(s['out_of_scope_abstention_rate'])}  (target 100%)",
        f"In-scope retrieval hit rate  : {pct(s['in_scope_retrieval_hit_rate'])}  (target ~100%)",
        f"In-scope retrieval page rate : {pct(s['in_scope_retrieval_page_rate'])}",
        f"In-scope citation page rate  : {pct(s['in_scope_citation_page_rate'])}",
        f"In-scope answered            : {s['in_scope_answered']}/{s['n_in_scope']}",
        f"In-scope answer-keyword rate : {pct(s['in_scope_keyword_rate'])}",
        f"Nearest distance, in-scope max / out-of-scope min : "
        f"{num(m['in_scope_max'])} / {num(m['out_of_scope_min'])}  "
        f"(current threshold {rp.DISTANCE_THRESHOLD})",
    ]
    n_out = s["n_out_of_scope"]
    if n_out:
        lines.append(
            f"Out-of-scope stopped by threshold / by model refusal : "
            f"{len(s['out_of_scope_threshold_ids'])} / "
            f"{len(s['out_of_scope_model_refused_ids'])} of {n_out}")
    if m["separable"]:
        lines.append(f"Suggested threshold (midpoint): {m['suggested_threshold']}")
    elif m["separable"] is False:
        if s["out_of_scope_answered_ids"]:
            lines.append("In-scope and out-of-scope distances OVERLAP and some out-of-scope "
                         "questions were answered: neither the threshold nor the model's "
                         "refusal caught them. Review those answers and the prompt.")
        else:
            lines.append("In-scope and out-of-scope distances OVERLAP, so the threshold alone "
                         "can't separate this set; the model's refusal caught the rest: "
                         f"{s['out_of_scope_model_refused_ids']}. Lowering the threshold "
                         "below the in-scope max would reject real questions.")
    for key, label in (("in_scope_abstained_ids", "In-scope questions that abstained"),
                       ("in_scope_keyword_fail_ids", "In-scope keyword misses"),
                       ("in_scope_page_miss_ids", "In-scope citation page misses"),
                       ("out_of_scope_answered_ids", "Out-of-scope questions that were answered")):
        if s.get(key):
            lines.append(f"{label}: {s[key]}")
    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--index", default=str(DEFAULT_INDEX),
                     help="Chroma persist dir to evaluate (default: app/demo_index)")
    src.add_argument("--pdf", default=None,
                     help="evaluate a policy PDF instead: builds an in-memory index "
                          "(costs one embedding pass) - use with your own --questions")
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    ap.add_argument("--results", default=str(DEFAULT_RESULTS))
    ap.add_argument("--no-cache", action="store_true", help="ignore cached results")
    ap.add_argument("--max-age-days", type=float, default=DEFAULT_MAX_AGE_DAYS,
                    help="re-run cached results older than this (0 = never expire)")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between API calls")
    args = ap.parse_args(argv)

    try:
        rp._read_api_key()  # fail fast, before opening anything
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if "latest" in rp.GEN_MODEL:
        print(f"note: '{rp.GEN_MODEL}' is a moving alias and the API doesn't report which "
              f"version served it, so cached results expire after {args.max_age_days:g} "
              "days. Pin INSURANCE_RAG_GEN_MODEL to a specific version for reproducible runs.")

    qset = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    if args.pdf:
        pdf = Path(args.pdf).resolve()
        collection, _ = rp.build_index_from_pdf(str(pdf), persist_dir=None,
                                                source_name=pdf.name)
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()[:12]
        index_label = f"pdf:{pdf.name}:{digest}"
    else:
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
        answer_fn=lambda q: rp.answer_question_detailed(collection, q),
        index_label=index_label,
        cache=cache,
        save_cache=_save,
        sleep_between=args.sleep,
        max_age_days=args.max_age_days or None,
    )
    print()
    print(format_summary(summary, index_label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
