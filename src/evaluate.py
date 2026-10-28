"""
evaluate.py — evaluation harness for Insurance-Policy-RAG.

Runs an eval set — by default eval/questions_v2.json (65 items) — against the
SAME pipeline code the app and API ship (src/rag_pipeline.py), on any Chroma
index: by default the bundled demo index at app/demo_index/, i.e. exactly what
production serves, or a PDF of your own (--pdf), to calibrate it. The v1 set
(notebooks/eval/eval_questions.json) still runs with --questions.

Each item is scored by its expected behaviour (answer / defer / abstain); the
metric definitions live in src/eval_metrics.py. All metrics are deterministic
(no LLM judge yet):
  * abstention precision / recall ("should abstain" = positive class), and
    whether each abstention came from the distance threshold or the model
  * retrieval hit rate, page hit@k, and recall@k of the evidence phrases
    (before and after the threshold)
  * citation accuracy: cited pages vs expected_pages, and whether the cited
    passages contain the item's evidence phrases
  * keyword rate, per-item pass/fail with reasons, per-behaviour and
    per-category breakdowns, and the in-scope vs out-of-scope distance margin
Abstention uses rag_pipeline.is_abstention, the same definition as the app/API.

Each run prints a summary and writes a markdown report plus a metrics JSON
(default eval/reports/<set version>_<date>.md/.json; see src/eval_report.py).

Free-tier safe: sequential, paced, and cached. The cache key includes the
question text, index path, model and threshold, so rewording a question or
switching index/model re-runs that question instead of reusing a stale result.
Scoring is re-applied to cached answers on every run, so editing an item's
expected pages, keywords or evidence takes effect without new API calls.
The generator model is pinned (rag_pipeline.GEN_MODEL), so cached answers stay
valid until something in the cache key changes. If you set a moving alias
such as "gemini-flash-latest" (its model can change and the endpoint doesn't
report which one served a request), cached answers expire after
--max-age-days (default 14 for an alias).

Run from the repo root (needs GEMINI_API_KEY):
    python -m src.evaluate                      # eval set v2 on the demo index
    python -m src.evaluate --questions notebooks/eval/eval_questions.json   # v1
    python -m src.evaluate --no-cache           # fresh answers for everything
    python -m src.evaluate --pdf my_policy.pdf --questions my_questions.json
                                                # calibrate a new policy
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import eval_metrics as em  # noqa: E402
from src import eval_report as er  # noqa: E402
from src import eval_set as es  # noqa: E402
from src import judge as jd  # noqa: E402
from src import rag_pipeline as rp  # noqa: E402

V2_QUESTIONS = REPO_ROOT / "eval" / "questions_v2.json"
V1_QUESTIONS = REPO_ROOT / "notebooks" / "eval" / "eval_questions.json"
V1_RESULTS = REPO_ROOT / "notebooks" / "eval" / "eval_results.json"
DEFAULT_QUESTIONS = V2_QUESTIONS
DEFAULT_INDEX = REPO_ROOT / "app" / "demo_index"
REPORTS_DIR = REPO_ROOT / "eval" / "reports"
DEFAULT_MAX_AGE_DAYS = 14.0


def default_max_age_days(model: str | None = None) -> float | None:
    """Cache expiry for answers: 14 days for a moving alias, never for a
    pinned model (its answers only change when the cache key does)."""
    return DEFAULT_MAX_AGE_DAYS if rp.is_moving_alias(model or rp.GEN_MODEL) else None


def results_path_for(questions_path: str | Path) -> Path:
    """Default answer cache for a question set: v1 keeps its historical file
    (notebooks/eval/eval_results.json); any other set gets
    <questions stem>_results.json next to it (git-ignored for eval/)."""
    q = Path(questions_path).resolve()
    if q == V1_QUESTIONS.resolve():
        return V1_RESULTS
    return q.with_name(q.stem + "_results.json")


DEFAULT_RESULTS = results_path_for(DEFAULT_QUESTIONS)

# Kept for callers of the v1 API (scoring helpers now live in eval_metrics).
contains_keywords = em.contains_keywords
page_hit = em.page_hit


def is_abstention(answer: str, idk: str = rp.IDK_ANSWER) -> bool:
    """Shared abstention definition (delegates to the pipeline's)."""
    return rp.is_abstention(answer, idk)


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


def score_record(rec: dict, q: dict, chunk_texts: dict[str, str] | None = None) -> dict:
    """(Re)compute a record's scoring fields from the CURRENT item definition
    (see eval_metrics.score_record)."""
    return em.score_record(rec, q, chunk_texts)


def _is_fresh(rec: dict, max_age_s: float | None, now: float) -> bool:
    if max_age_s is None:
        return True
    ts = rec.get("evaluated_at")
    return isinstance(ts, (int, float)) and now - ts <= max_age_s


def _record_from_result(q: dict, res: dict, index_label: str, now: float) -> dict:
    """What gets cached for one question: the pipeline's output, no scoring and
    no chunk text (so a private policy's cache holds only answers and ids)."""
    retrieved = res.get("retrieved") or []
    candidates = res.get("candidates")
    return {
        "id": q["id"], "question": q["question"],
        "answer": res["answer"], "pages": res.get("pages") or [],
        "cited_ids": list(res.get("cited_ids") or []),
        "retrieved_ids": [r.get("id") for r in retrieved if r.get("id") is not None],
        "retrieved_pages": sorted({
            r.get("metadata", {}).get("page") for r in retrieved
            if r.get("metadata", {}).get("page") is not None
        }),
        "n_retrieved": len(retrieved),
        # every top-k chunk BEFORE the threshold: id, page, distance (no text)
        "candidates": None if candidates is None else [
            {"id": c.get("id"), "page": c.get("page"), "distance": c.get("distance")}
            for c in candidates
        ],
        # closest chunk BEFORE thresholding (calibration signal)
        "nearest_distance": res.get("nearest_distance"),
        # closest chunk that PASSED the threshold (legacy field)
        "top_distance": min(
            (r["score"] for r in retrieved if r.get("score") is not None), default=None,
        ),
        "abstained": bool(res["abstained"]),
        "citations_verified": res.get("citations_verified"),
        "finish_reason": res.get("finish_reason"),
        "generation_calls": _generation_calls(res),
        "index": index_label, "model": rp.GEN_MODEL,
        "model_resolved": res.get("model_resolved"),
        "evaluated_at": now,
    }


def _generation_calls(res: dict) -> int:
    """Generation requests one answer cost. Older pipelines / test fakes don't
    report it: assume one call whenever something passed the threshold."""
    n = res.get("generation_calls")
    if isinstance(n, int):
        return n
    return 1 if res.get("retrieved") else 0


class EvalIncomplete(RuntimeError):
    """The run stopped before every question had an answer: the daily Gemini
    quota ran out or --max-calls was reached. Answers so far are cached, so
    running again continues where this run stopped."""

    def __init__(self, reason: str, done: int, total: int, new: int, calls: int,
                 skipped_ids: list[str], retry_after_s: float | None = None,
                 records: list[dict] | None = None):
        super().__init__(reason)
        self.reason, self.done, self.total = reason, done, total
        self.new, self.calls, self.skipped_ids = new, calls, skipped_ids
        self.retry_after_s = retry_after_s
        self.records = records or []  # the scored records that do have answers

    def message(self) -> str:
        return (f"Stopped early: {self.reason}\n"
                f"{self.done}/{self.total} questions have answers ({self.new} new this run, "
                f"{self.calls} generation call(s)). They are cached: run `make eval` again "
                "later to continue from here. No report is written until all questions "
                "are answered, so the numbers above are not a result yet.")


_TAG = {"answer": "ANS", "defer": "DEF", "abstain": "ABS"}


def _log_line(rec: dict) -> str:
    dist = rec.get("nearest_distance")
    dist_s = "n/a" if dist is None else f"{dist:.3f}"
    how = ((" (threshold)" if rec["abstention_layer"] == "threshold" else " (model refused)")
           if rec.get("abstained") else "")
    verdict = "pass" if rec["item_pass"] else "FAIL: " + "; ".join(rec["fail_reasons"])
    return (f"{_TAG.get(rec['behavior'], rec['behavior'])} {rec['id']}: nearest={dist_s} "
            f"retrieved={rec['n_retrieved']} abstained={rec['abstained']}{how} {verdict}")


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
    chunk_texts: dict[str, str] | None = None,
    max_calls: int | None = None,
) -> tuple[list[dict], dict]:
    """Run every question through answer_fn and return (records, summary).

    qset is a v2 eval set or a v1 one (converted by eval_set.items_of).
    answer_fn(question) -> answer_question_detailed()-style dict (preferred)
    or the legacy (answer, pages, retrieved) tuple, with the collection
    already bound. Kept injectable so the harness itself can be unit-tested
    without an API key. Cached records older than max_age_days are re-run
    (None = never expire). Scoring is recomputed for cached records too, so
    edits to the set's expectations always apply. chunk_texts (chunk id ->
    text of the evaluated index) enables the evidence metrics.

    Budget: max_calls caps the generation calls this run may make (checked
    before each uncached question, so a truncated answer's retry can take it
    one over). When the cap is reached or Gemini reports its daily quota is
    used up, uncached questions are skipped (cached ones are still scored) and
    EvalIncomplete is raised at the end instead of returning a summary.
    """
    cache = {} if cache is None else cache
    idk = qset.get("idk_answer", rp.IDK_ANSWER)
    max_age_s = None if max_age_days is None else max_age_days * 86400
    records: list[dict] = []
    items = es.items_of(qset)
    calls = new = 0
    stop_reason: str | None = None
    retry_after_s: float | None = None
    skipped: list[str] = []

    for q in items:
        key = _cache_key(q, index_label)
        if key in cache and _is_fresh(cache[key], max_age_s, clock()):
            rec = cache[key]
        else:
            if stop_reason is None and max_calls is not None and calls >= max_calls:
                stop_reason = f"reached --max-calls {max_calls}."
            if stop_reason is not None:
                skipped.append(q["id"])
                continue
            try:
                out = answer_fn(q["question"])
            except rp.GeminiQuotaExhaustedError as exc:
                stop_reason, retry_after_s = str(exc), exc.retry_after_s
                skipped.append(q["id"])
                log(f"STOP {q['id']}: {exc}")
                continue
            res = _normalize_result(out, idk)
            rec = _record_from_result(q, res, index_label, clock())
            calls += rec["generation_calls"]
            new += 1
            cache[key] = rec
            if save_cache:
                save_cache(cache)  # incremental: a crash never loses progress
            if sleep_between:
                time.sleep(sleep_between)
        score_record(rec, q, chunk_texts)
        records.append(rec)
        log(_log_line(rec))

    if skipped:
        raise EvalIncomplete(stop_reason or "stopped.", done=len(records), total=len(items),
                             new=new, calls=calls, skipped_ids=skipped,
                             retry_after_s=retry_after_s, records=records)
    return records, summarize(records, category_order=list(qset.get("categories") or []))


def cached_records(qset: dict, index_label: str, cache: dict,
                   chunk_texts: dict[str, str] | None = None,
                   max_age_days: float | None = DEFAULT_MAX_AGE_DAYS) -> tuple[list[dict], int]:
    """The scored records of every question that already has a (fresh) cached
    answer, without any API call; returns (records, number of questions)."""
    def _no_calls(_question):
        raise AssertionError("cached_records must not call the API")

    try:
        records, _ = run_eval(qset, _no_calls, index_label, cache=cache, sleep_between=0,
                              log=lambda _: None, max_age_days=max_age_days,
                              chunk_texts=chunk_texts, max_calls=0)
    except EvalIncomplete as stop:
        records = stop.records
    return records, len(es.items_of(qset))


def add_judge_results(summary: dict, records: list[dict], qset: dict,
                      questions_path: str | Path) -> None:
    """Attach cached LLM-judge scores (src/judge.py) to the records and add a
    "judge" section to the summary, if any judgments exist for this set."""
    judge_cache = jd.load_json(jd.judge_path_for(questions_path))
    human_rows = jd.load_human_scores(jd.human_scores_path_for(questions_path))
    if not judge_cache and not human_rows:
        return
    prompt = jd.load_prompt()
    items_by_id = {i["id"]: i for i in es.items_of(qset)}
    jd.attach_judgments(records, items_by_id, judge_cache, prompt, jd.JUDGE_MODEL)
    summary["judge"] = jd.summarize_judge(records, prompt, jd.JUDGE_MODEL,
                                          list(qset.get("categories") or []), human_rows)


def suggest_threshold(records: list[dict]) -> dict:
    """From nearest (pre-threshold) distances, report the separation between
    questions that should be answered (answer/defer) and those that should
    abstain, and a midpoint threshold if they are separable.
    Distances: lower = more similar."""
    ins = [r["nearest_distance"] for r in records
           if r["behavior"] in em.SHOULD_ANSWER and r.get("nearest_distance") is not None]
    outs = [r["nearest_distance"] for r in records
            if r["behavior"] == "abstain" and r.get("nearest_distance") is not None]
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


def summarize(records: list[dict], category_order: list[str] | None = None) -> dict:
    """All metrics. The flat in_scope_* / out_of_scope_* keys are the v1
    summary (in-scope = answer + defer items, out-of-scope = abstain items),
    kept so v1 numbers stay comparable with earlier runs; the v2 metrics are
    under overall / abstention / by_behavior / by_category / failures."""
    ins = [r for r in records if r["behavior"] in em.SHOULD_ANSWER]
    outs = [r for r in records if r["behavior"] == "abstain"]
    calibrated = [r for r in ins if r.get("keyword_pass") is not None]
    paged_retr = [r for r in ins if r.get("retrieval_page_hit") is not None]
    paged_cite = [r for r in ins if r.get("citation_page_hit") is not None]
    rate = em.rate
    models = sorted({r.get("model_resolved") for r in records if r.get("model_resolved")})
    summary = {
        "n_items": len(records),
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
    summary.update(em.summarize_items(records, category_order))
    return summary


def format_summary(s: dict, index_label: str) -> str:
    """Short console summary; the full breakdown is in the markdown report."""
    pct = er.pct
    num = er.num
    m = s["distance_margin"]
    resolved_list = s.get("models_resolved") or []
    if not resolved_list:
        resolved = "not reported"
    elif resolved_list == [rp.GEN_MODEL]:
        resolved = "exact version not reported by the API"
    else:
        resolved = ", ".join(resolved_list)
    o = s.get("overall") or {}
    a = s.get("abstention") or {}
    lines = [
        f"=== Evaluation summary (index: {index_label}, model: {rp.GEN_MODEL} -> {resolved}) ===",
        f"Items passed                 : {o.get('n_pass', 'n/a')}/{s['n_items']}  "
        f"({pct(o.get('pass_rate'))})",
        f"Abstention precision / recall: {pct(a.get('precision'))} / {pct(a.get('recall'))}  "
        f"(should-abstain items: {s['n_out_of_scope']}; target 100% / 100%)",
        f"Out-of-scope abstention rate : {pct(s['out_of_scope_abstention_rate'])}  (target 100%)",
        f"In-scope answered            : {s['in_scope_answered']}/{s['n_in_scope']}",
        f"In-scope retrieval hit rate  : {pct(s['in_scope_retrieval_hit_rate'])}  (target ~100%)",
        f"Recall@k (after / before threshold): {pct(o.get('recall_at_k'))} / "
        f"{pct(o.get('recall_at_k_pre_threshold'))}",
        f"Cited page hit / precision   : {pct(o.get('cited_page_hit'))} / "
        f"{pct(o.get('cited_page_precision'))}  (of answered)",
        f"Citation evidence hit        : {pct(o.get('evidence_hit'))}  (of answered; "
        f"coverage {pct(o.get('evidence_coverage'))})",
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
    failures = s.get("failures") or []
    if failures:
        lines.append(f"Failed items ({len(failures)}): " + ", ".join(f["id"] for f in failures))
    j = s.get("judge")
    if j:
        g = j["overall"]
        lines.append(
            f"LLM judge ({j['model']}, {j['prompt']}): judged {g['n_judged']}/{g['n_eligible']}; "
            f"fully correct {pct(g['fully_correct'])}, fully faithful {pct(g['fully_faithful'])}, "
            f"hallucination {pct(g['hallucination_rate'])}; strict pass "
            f"{pct(g['strict_pass_rate']) if g['strict_pass_rate'] is not None else 'n/a (judge incomplete)'}")
    return "\n".join(lines)


def _git_commit() -> str | None:
    """Short commit of the code that ran, with a marker if src/ has local edits."""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=REPO_ROOT,
                               capture_output=True, text=True, check=True).stdout.strip()
        return sha + (" (with uncommitted changes in src/)" if dirty else "")
    except Exception:
        return None


# --- CLI ---------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--index", default=str(DEFAULT_INDEX),
                     help="Chroma persist dir to evaluate (default: app/demo_index)")
    src.add_argument("--pdf", default=None,
                     help="evaluate a policy PDF instead: builds an in-memory index "
                          "(costs one embedding pass) - use with your own --questions")
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS),
                    help="eval set, v2 or v1 format (default: eval/questions_v2.json)")
    ap.add_argument("--results", default=None,
                    help="answer cache (default: <questions>_results.json next to the set; "
                         "notebooks/eval/eval_results.json for v1)")
    ap.add_argument("--report", default=None,
                    help="markdown report path; a metrics .json is written next to it "
                         "(default: eval/reports/<set version>_<date>.md; for --pdf, next "
                         "to the results file)")
    ap.add_argument("--no-report", action="store_true", help="only print the summary")
    ap.add_argument("--no-cache", action="store_true", help="ignore cached results")
    ap.add_argument("--max-age-days", type=float, default=None,
                    help="re-run cached results older than this (0 = never expire; "
                         "default: never for a pinned model, 14 for a '-latest' alias)")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between API calls")
    ap.add_argument("--max-calls", type=int, default=None,
                    help="stop after this many generation calls (cached answers are free); "
                         "run again later to continue. Useful on the free tier's daily limit")
    args = ap.parse_args(argv)

    questions_path = Path(args.questions)
    qset = es.load_eval_set(questions_path)
    if not es.is_v1(qset):
        problems = es.validate_eval_set(qset)
        if problems:
            print("error: the eval set is invalid (fix it, then run python -m src.eval_set):\n  "
                  + "\n  ".join(problems), file=sys.stderr)
            return 2

    try:
        rp._read_api_key()  # fail fast, before opening anything
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    max_age_days = (default_max_age_days() if args.max_age_days is None
                    else (args.max_age_days or None))
    if rp.is_moving_alias(rp.GEN_MODEL):
        print(f"note: '{rp.GEN_MODEL}' is a moving alias and the API doesn't report which "
              f"version served it, so cached results expire after {max_age_days or 0:g} "
              "days. Pin INSURANCE_RAG_GEN_MODEL to a specific version for reproducible runs.")

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
    n_chunks = collection.count()
    print(f"Index: {index_label} ({n_chunks} chunks)")
    print(f"Eval set: {questions_path} ({es.set_version(qset)}, "
          f"{len(es.items_of(qset))} items)")
    # Chunk text, for checking cited passages against evidence phrases. Held in
    # memory for scoring only; never written to the cache or the report.
    chunk_texts = {c["id"]: c["text"] for c in es.chunks_from_collection(collection)}

    results_path = Path(args.results) if args.results else results_path_for(questions_path)
    cache = {}
    if not args.no_cache and results_path.exists():
        cache = json.loads(results_path.read_text(encoding="utf-8"))

    def _save(c):
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        records, summary = run_eval(
            qset,
            answer_fn=lambda q: rp.answer_question_detailed(collection, q),
            index_label=index_label,
            cache=cache,
            save_cache=_save,
            sleep_between=args.sleep,
            max_age_days=max_age_days,
            chunk_texts=chunk_texts,
            max_calls=args.max_calls,
        )
    except EvalIncomplete as stop:
        print()
        print(stop.message())
        return 3
    except rp.GeminiUnavailableError as exc:  # transient errors outlasted the retries
        print(f"\nStopped: {exc}\nAnswers so far are cached; run `make eval` again to "
              "continue.", file=sys.stderr)
        return 3
    add_judge_results(summary, records, qset, questions_path)
    print()
    print(format_summary(summary, index_label))

    if not args.no_report:
        today = _dt.date.today().isoformat()
        version = es.set_version(qset)
        if args.report:
            report_path = Path(args.report)
        elif args.pdf:
            report_path = results_path.with_name(results_path.stem + f"_report_{today}.md")
        else:
            report_path = REPORTS_DIR / f"{version}_{today}.md"
        meta = {
            "date": today,
            "eval_set": str(questions_path),
            "eval_set_version": version,
            "n_items": len(records),
            "index": index_label,
            "n_chunks": n_chunks,
            "gen_model": rp.GEN_MODEL,
            "models_resolved": summary.get("models_resolved") or [],
            "embed_model": rp.EMBED_MODEL,
            "k": rp.K_DEFAULT,
            "threshold": rp.DISTANCE_THRESHOLD,
            "chunk_size": rp.CHUNK_SIZE,
            "chunk_overlap": rp.CHUNK_OVERLAP,
            "encoding": rp.ENCODING_NAME,
            "git_commit": _git_commit(),
        }
        md_path, json_path = er.write_report(report_path, summary, records, meta)
        print(f"\nReport: {md_path}\nMetrics: {json_path}")
        if args.pdf:
            print("note: this report quotes answers about your PDF; keep it out of the repo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
