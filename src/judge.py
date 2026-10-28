"""
judge.py — LLM-as-judge for the evaluation harness (M1c).

A second, pinned model reads each answered question and scores, on a 0-2
scale (rubric in eval/prompts/judge_v1.md):
  * faithfulness  every claim in the answer is supported by the passages the
                  pipeline retrieved (catches hallucination)
  * correctness   the answer matches the eval set's reference answer
Only items that should be answered (behaviour answer/defer), were answered,
and showed the right behaviour are judged; everything else is already decided
by the judge-free checks (src/eval_metrics.py).

Design (see PLAN.md, M1c and decisions D4, D13):
  * The judge model is PINNED and differs from the generator
    (INSURANCE_RAG_JUDGE_MODEL), so scores don't drift with a "-latest" alias
    and the generator isn't grading itself. On the free tier each model has
    its own daily quota, so judging doesn't use the generator's.
  * The prompt is a versioned file; its name and hash are part of the cache
    key and the report.
  * Separate step from answering: `make judge` reads the cached answers,
    judges the ones not judged yet, and caches the judgments
    (eval/<set>_judge.json, git-ignored). It is budgeted (--max-calls) and
    stops at once when the daily quota is used up; run it again to continue.
    `make eval` then puts the judge scores in the report, with coverage.
  * Human check: `make judge-sheet` samples ~20 judged-eligible items for the
    owner to score by hand (eval/<set>_judge_sheet.md + _human_scores.csv);
    the report shows judge-human agreement (exact, within one, weighted kappa).

CLI (from the repo root):
    python -m src.judge                    # judge cached answers (needs GEMINI_API_KEY)
    python -m src.judge --max-calls 10     # at most 10 judge calls this run
    python -m src.judge --sheet            # write the human scoring sheet (no API calls)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import eval_metrics as em  # noqa: E402
from src import rag_pipeline as rp  # noqa: E402

JUDGE_MODEL = os.environ.get("INSURANCE_RAG_JUDGE_MODEL", "gemini-3.6-flash")
JUDGE_PROMPT_PATH = Path(os.environ.get(
    "INSURANCE_RAG_JUDGE_PROMPT", REPO_ROOT / "eval" / "prompts" / "judge_v1.md"))
JUDGE_MAX_TOKENS = int(os.environ.get("INSURANCE_RAG_JUDGE_MAX_TOKENS", "512"))
JUDGE_REASONING_EFFORT = os.environ.get("INSURANCE_RAG_JUDGE_REASONING_EFFORT", "none")
SCALE = (0, 1, 2)
DEFAULT_SAMPLE_SIZE = 20
DEFAULT_SEED = 13

BEHAVIOUR_NOTES = {
    "answer": "The policy answers this question. A correct answer states it and "
              "is supported by the passages.",
    "defer": "The policy does not state this detail itself: it refers to the "
             "Schedule of Benefits, a separate document. A correct answer says the "
             "detail is in the Schedule of Benefits (and may add what the policy "
             "does say); it must not invent an amount.",
}


# --- prompt ------------------------------------------------------------------------
@dataclass(frozen=True)
class Prompt:
    name: str     # file stem, e.g. "judge_v1"
    sha: str      # first 12 hex chars of the file's sha256
    system: str
    user: str
    rubric: str


def _section(text: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        raise ValueError(f"judge prompt has no '## {title}' section")
    return m.group(1).strip()


def load_prompt(path: str | Path = JUDGE_PROMPT_PATH) -> Prompt:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    rubric = _section(text, "Rubric")
    return Prompt(
        name=path.stem,
        sha=hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        system=_section(text, "System message").replace("{{rubric}}", rubric),
        user=_section(text, "User message"),
        rubric=rubric,
    )


def eligible(rec: dict) -> bool:
    """Judged items: should be answered, were answered, right behaviour."""
    return (rec.get("behavior") in em.SHOULD_ANSWER and not rec.get("abstained")
            and bool(rec.get("behavior_correct")))


def passages_for(rec: dict, chunk_texts: dict[str, str]) -> list[tuple[str, str]]:
    """The passages the generator saw (after the threshold), as (id, text)."""
    return [(i, chunk_texts[i]) for i in rec.get("retrieved_ids") or [] if i in chunk_texts]


def render_messages(prompt: Prompt, item: dict, rec: dict,
                    chunk_texts: dict[str, str]) -> list[dict]:
    passages = "\n\n---\n\n".join(f"[{i}] {t}" for i, t in passages_for(rec, chunk_texts))
    user = prompt.user
    for key, value in (
        ("question", item["question"]),
        ("expected_behaviour", BEHAVIOUR_NOTES.get(item["behavior"], "")),
        ("reference_answer", item.get("reference_answer") or ""),
        ("passages", passages or "(none)"),
        ("answer", rec.get("answer") or ""),
    ):
        user = user.replace("{{" + key + "}}", value)
    return [{"role": "system", "content": prompt.system}, {"role": "user", "content": user}]


def answer_sha(answer: str) -> str:
    return hashlib.sha256((answer or "").encode("utf-8")).hexdigest()[:12]


def judge_key(item: dict, rec: dict, model: str, prompt: Prompt) -> str:
    """Cache key: changes when anything the judgment depends on changes."""
    raw = json.dumps([item["id"], item["question"], item["behavior"],
                      item.get("reference_answer"), rec.get("answer"),
                      rec.get("retrieved_ids"), rec.get("index"), model, prompt.sha])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# --- parsing ---------------------------------------------------------------------------
class JudgeParseError(ValueError):
    """The judge's reply wasn't the JSON object the prompt asks for."""


def _score(data: dict, key: str) -> int:
    v = data.get(key)
    if isinstance(v, str) and v.strip().isdigit():
        v = int(v.strip())
    if isinstance(v, bool) or not isinstance(v, int) or v not in SCALE:
        raise JudgeParseError(f"'{key}' must be 0, 1 or 2, got {v!r}")
    return v


def parse_judgment(text: str) -> dict:
    """Parse the judge's reply: one JSON object, possibly inside a ``` fence
    or with stray text around it. Raises JudgeParseError otherwise."""
    t = (text or "").strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end <= start:
        raise JudgeParseError("no JSON object in the reply")
    try:
        data = json.loads(t[start:end + 1])
    except json.JSONDecodeError as exc:
        raise JudgeParseError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise JudgeParseError("the reply is not a JSON object")
    claims = data.get("unsupported_claims") or []
    if not isinstance(claims, list):
        claims = [str(claims)]
    return {
        "faithfulness": _score(data, "faithfulness"),
        "correctness": _score(data, "correctness"),
        "reason": str(data.get("reason") or "").strip(),
        "unsupported_claims": [str(c) for c in claims if str(c).strip()],
    }


def make_judge_fn(model: str = JUDGE_MODEL) -> Callable[[list[dict]], str]:
    """messages -> reply text, through the pipeline's client and retry policy
    (a used-up daily quota raises GeminiQuotaExhaustedError at once)."""
    client = rp.get_client()
    extra_body = {"reasoning_effort": JUDGE_REASONING_EFFORT} if JUDGE_REASONING_EFFORT else None

    def judge(messages: list[dict]) -> str:
        kwargs = dict(model=model, messages=messages, temperature=0.0,
                      max_tokens=JUDGE_MAX_TOKENS)
        if extra_body:
            kwargs["extra_body"] = extra_body
        resp = rp._call_with_backoff(lambda: client.chat.completions.create(**kwargs), "judging")
        return resp.choices[0].message.content or ""
    return judge


# --- running ------------------------------------------------------------------------------
def run_judge(
    records: list[dict],
    items_by_id: dict[str, dict],
    chunk_texts: dict[str, str],
    judge_fn: Callable[[list[dict]], str],
    cache: dict,
    prompt: Prompt,
    model: str = JUDGE_MODEL,
    save_cache: Callable[[dict], None] | None = None,
    max_calls: int | None = None,
    sleep_between: float = 2.0,
    log: Callable[[str], None] = print,
    clock: Callable[[], float] = time.time,
) -> dict:
    """Judge every eligible record that has no cached judgment yet.

    Stops asking (and reports why) when max_calls is reached or the daily
    quota is used up; a reply that can't be parsed is logged and retried on
    the next run. Returns run statistics."""
    stats = {"eligible": 0, "judged": 0, "new": 0, "calls": 0, "parse_errors": [],
             "remaining": [], "stop_reason": None, "retry_after_s": None}
    for rec in records:
        if not eligible(rec):
            continue
        stats["eligible"] += 1
        item = items_by_id[rec["id"]]
        key = judge_key(item, rec, model, prompt)
        if key in cache:
            stats["judged"] += 1
            continue
        if stats["stop_reason"] is None and max_calls is not None and stats["calls"] >= max_calls:
            stats["stop_reason"] = f"reached --max-calls {max_calls}."
        if stats["stop_reason"] is not None:
            stats["remaining"].append(rec["id"])
            continue
        try:
            reply = judge_fn(render_messages(prompt, item, rec, chunk_texts))
        except rp.GeminiQuotaExhaustedError as exc:
            stats["stop_reason"], stats["retry_after_s"] = str(exc), exc.retry_after_s
            stats["remaining"].append(rec["id"])
            log(f"STOP {rec['id']}: {exc}")
            continue
        stats["calls"] += 1
        try:
            judgment = parse_judgment(reply)
        except JudgeParseError as exc:
            stats["parse_errors"].append(rec["id"])
            stats["remaining"].append(rec["id"])
            log(f"JUDGE {rec['id']}: unreadable reply ({exc}); will retry next run")
        else:
            cache[key] = {**judgment, "id": rec["id"], "model": model,
                          "prompt": prompt.name, "prompt_sha": prompt.sha,
                          "answer_sha": answer_sha(rec.get("answer", "")),
                          "judged_at": clock()}
            stats["judged"] += 1
            stats["new"] += 1
            log(f"JUDGE {rec['id']}: faithfulness={judgment['faithfulness']} "
                f"correctness={judgment['correctness']}  {judgment['reason']}")
            if save_cache:
                save_cache(cache)
        if sleep_between:
            time.sleep(sleep_between)
    return stats


def attach_judgments(records: list[dict], items_by_id: dict[str, dict], cache: dict,
                     prompt: Prompt, model: str = JUDGE_MODEL) -> None:
    """Add judge fields to scored records (in place):
    judge_eligible, judge (the cached judgment or None) and strict_pass:
    the judge-free pass AND faithfulness 2 AND correctness 2 for judged items
    (None while an eligible item is still unjudged)."""
    for rec in records:
        elig = eligible(rec)
        j = cache.get(judge_key(items_by_id[rec["id"]], rec, model, prompt)) if elig else None
        rec["judge_eligible"] = elig
        rec["judge"] = j
        if not rec.get("item_pass"):
            rec["strict_pass"] = False
        elif rec["behavior"] == "abstain":
            rec["strict_pass"] = True
        elif j is None:
            rec["strict_pass"] = None
        else:
            rec["strict_pass"] = j["faithfulness"] == 2 and j["correctness"] == 2


# --- metrics --------------------------------------------------------------------------------
def _judge_group(records: list[dict]) -> dict:
    elig = [r for r in records if r.get("judge_eligible")]
    judged = [r["judge"] for r in elig if r.get("judge")]
    f = [j["faithfulness"] for j in judged]
    c = [j["correctness"] for j in judged]
    complete = len(judged) == len(elig)
    return {
        "n_eligible": len(elig),
        "n_judged": len(judged),
        "coverage": em.rate(len(judged), len(elig)),
        "mean_faithfulness": em.mean(f),
        "mean_correctness": em.mean(c),
        "fully_faithful": em.mean(x == 2 for x in f),
        "fully_correct": em.mean(x == 2 for x in c),
        "hallucination_rate": em.mean(x == 0 for x in f),
        # Only meaningful once every eligible item has been judged.
        "strict_pass_rate": (em.rate(sum(bool(r.get("strict_pass")) for r in records),
                                     len(records)) if complete and records else None),
    }


def weighted_kappa(a: list[int], b: list[int], k: int = len(SCALE)) -> float | None:
    """Quadratic-weighted Cohen's kappa for two raters on a 0..k-1 scale.
    None when undefined (no pairs, or no variation to compare)."""
    n = len(a)
    if n == 0 or n != len(b):
        return None
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x][y] += 1
    rows = [sum(obs[i]) for i in range(k)]
    cols = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = [[(i - j) ** 2 / (k - 1) ** 2 for j in range(k)] for i in range(k)]
    num = sum(w[i][j] * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w[i][j] * rows[i] * cols[j] / n for i in range(k) for j in range(k))
    return None if den == 0 else 1 - num / den


def agreement(records: list[dict], human_rows: list[dict]) -> dict | None:
    """Judge vs human scores on the sampled items. A human score only counts
    if it was given for the answer that was judged (same answer_sha): when an
    answer is regenerated, its old human score is reported as stale."""
    by_id = {r["id"]: r for r in records}
    pairs: dict[str, list[tuple[int, int]]] = {"faithfulness": [], "correctness": []}
    stale, unjudged = [], []
    for row in human_rows:
        rec = by_id.get(row["id"])
        if rec is None or rec.get("judge") is None:
            unjudged.append(row["id"])
            continue
        if row.get("answer_sha") != answer_sha(rec.get("answer", "")):
            stale.append(row["id"])
            continue
        for dim in pairs:
            if row.get(dim) is not None:
                pairs[dim].append((rec["judge"][dim], row[dim]))
    if not any(pairs.values()):
        return None if not (stale or unjudged) else {"stale_ids": stale,
                                                     "unjudged_ids": unjudged, "dims": {}}
    dims = {}
    for dim, ps in pairs.items():
        judge_s, human_s = [p[0] for p in ps], [p[1] for p in ps]
        dims[dim] = {
            "n": len(ps),
            "exact": em.mean(x == y for x, y in ps),
            "within_one": em.mean(abs(x - y) <= 1 for x, y in ps),
            "weighted_kappa": weighted_kappa(judge_s, human_s),
            "judge_mean": em.mean(judge_s),
            "human_mean": em.mean(human_s),
        }
    return {"dims": dims, "stale_ids": stale, "unjudged_ids": unjudged}


def summarize_judge(records: list[dict], prompt: Prompt, model: str = JUDGE_MODEL,
                    category_order: list[str] | None = None,
                    human_rows: list[dict] | None = None) -> dict:
    cats = list(category_order or [])
    cats += sorted({r["category"] for r in records} - set(cats))
    return {
        "model": model,
        "prompt": prompt.name,
        "prompt_sha": prompt.sha,
        "overall": _judge_group(records),
        "by_category": {c: _judge_group([r for r in records if r["category"] == c])
                        for c in cats
                        if any(r["category"] == c and r.get("judge_eligible") for r in records)},
        "below_full": [
            {"id": r["id"], "category": r["category"],
             "faithfulness": r["judge"]["faithfulness"],
             "correctness": r["judge"]["correctness"],
             "reason": r["judge"].get("reason", ""),
             "unsupported_claims": r["judge"].get("unsupported_claims", [])}
            for r in records
            if r.get("judge") and (r["judge"]["faithfulness"] < 2 or r["judge"]["correctness"] < 2)
        ],
        "agreement": agreement(records, human_rows) if human_rows else None,
    }


# --- files ------------------------------------------------------------------------------------
def judge_path_for(questions_path: str | Path) -> Path:
    q = Path(questions_path)
    return q.with_name(q.stem + "_judge.json")


def human_scores_path_for(questions_path: str | Path) -> Path:
    q = Path(questions_path)
    return q.with_name(q.stem + "_human_scores.csv")


def sheet_path_for(questions_path: str | Path) -> Path:
    q = Path(questions_path)
    return q.with_name(q.stem + "_judge_sheet.md")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


HUMAN_COLUMNS = ["id", "answer_sha", "faithfulness", "correctness", "notes"]


def load_human_scores(path: str | Path) -> list[dict]:
    """Rows of the human scoring CSV; blank scores become None."""
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out = {"id": (row.get("id") or "").strip(),
                   "answer_sha": (row.get("answer_sha") or "").strip()}
            for dim in ("faithfulness", "correctness"):
                v = (row.get(dim) or "").strip()
                if v and (not v.isdigit() or int(v) not in SCALE):
                    raise ValueError(f"{path.name}: {out['id']}: {dim} must be 0, 1 or 2, "
                                     f"got {v!r}")
                out[dim] = int(v) if v else None
            if out["id"]:
                rows.append(out)
    return rows


def sample_for_sheet(records: list[dict], n: int = DEFAULT_SAMPLE_SIZE,
                     seed: int = DEFAULT_SEED,
                     category_order: list[str] | None = None) -> list[dict]:
    """Up to n eligible records, spread across categories (round-robin over
    categories, each shuffled with a fixed seed), so the same answers always
    give the same sample."""
    rng = random.Random(seed)
    cats = list(category_order or [])
    cats += sorted({r["category"] for r in records} - set(cats))
    pools = []
    for c in cats:
        pool = sorted((r for r in records if r["category"] == c and eligible(r)),
                      key=lambda r: r["id"])
        rng.shuffle(pool)
        if pool:
            pools.append(pool)
    picked: list[dict] = []
    while len(picked) < n and any(pools):
        for pool in pools:
            if pool and len(picked) < n:
                picked.append(pool.pop(0))
    return picked


def _quote(text: str) -> str:
    return "\n".join("> " + line if line.strip() else ">" for line in (text or "").splitlines())


def render_sheet(sample: list[dict], items_by_id: dict[str, dict],
                 chunk_texts: dict[str, str], prompt: Prompt, set_name: str) -> str:
    out = [
        f"# Human scoring sheet — eval set {set_name}",
        "",
        "Score each answer yourself, **before** looking at the judge's scores, and "
        f"enter the numbers in `{Path(set_name).stem}_human_scores.csv` (same folder). "
        "Use the same rubric the judge uses:",
        "",
        prompt.rubric,
        "",
        f"Sample: {len(sample)} answered items, spread across categories (fixed seed). "
        "Generated by `python -m src.judge --sheet`; regenerate only if the answers change.",
    ]
    for rec in sample:
        item = items_by_id[rec["id"]]
        out += ["", "---", "", f"## {rec['id']} ({rec['category']}, {rec['behavior']})", "",
                f"**Question:** {item['question']}", "",
                f"**Expected:** {BEHAVIOUR_NOTES.get(item['behavior'], '')}", "",
                f"**Reference answer:** {item.get('reference_answer', '')}", "",
                "**Passages the system saw:**", ""]
        for pid, text in passages_for(rec, chunk_texts):
            out += [f"*{pid}*", "", _quote(text), ""]
        out += ["**System answer:**", "", _quote(rec.get("answer", "")), ""]
    return "\n".join(out) + "\n"


def write_human_csv(path: Path, sample: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HUMAN_COLUMNS)
        w.writeheader()
        for rec in sample:
            w.writerow({"id": rec["id"], "answer_sha": answer_sha(rec.get("answer", "")),
                        "faithfulness": "", "correctness": "", "notes": ""})


# --- CLI ------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    from src import eval_set as es
    from src import evaluate as ev

    ap = argparse.ArgumentParser(description="LLM judge for cached evaluation answers.")
    ap.add_argument("--questions", default=str(ev.DEFAULT_QUESTIONS))
    ap.add_argument("--index", default=str(ev.DEFAULT_INDEX))
    ap.add_argument("--results", default=None, help="answer cache (default: as make eval)")
    ap.add_argument("--max-calls", type=int, default=None,
                    help="stop after this many judge calls; run again later to continue")
    ap.add_argument("--sleep", type=float, default=2.0, help="seconds between judge calls")
    ap.add_argument("--sheet", action="store_true",
                    help="write the human scoring sheet + CSV instead of judging (no API calls)")
    ap.add_argument("--sample-size", type=int, default=DEFAULT_SAMPLE_SIZE)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--force", action="store_true",
                    help="with --sheet: overwrite a human-scores CSV that already has scores")
    args = ap.parse_args(argv)

    questions_path = Path(args.questions)
    qset = es.load_eval_set(questions_path)
    if not es.is_v1(qset) and es.validate_eval_set(qset):
        print("error: the eval set is invalid; run python -m src.eval_set", file=sys.stderr)
        return 2
    items_by_id = {i["id"]: i for i in es.items_of(qset)}
    categories = list(qset.get("categories") or [])

    collection = rp.load_persistent_collection(persist_dir=args.index)
    try:
        index_label = str(Path(args.index).resolve().relative_to(REPO_ROOT))
    except ValueError:
        index_label = str(Path(args.index).resolve())
    chunk_texts = {c["id"]: c["text"] for c in es.chunks_from_collection(collection)}
    results_path = Path(args.results) if args.results else ev.results_path_for(questions_path)
    answers = load_json(results_path)
    records, total = ev.cached_records(qset, index_label, answers, chunk_texts)
    print(f"Answers cached: {len(records)}/{total} (from {results_path.name}).")
    prompt = load_prompt()

    if args.sheet:
        csv_path = human_scores_path_for(questions_path)
        if any(r["faithfulness"] is not None or r["correctness"] is not None
               for r in load_human_scores(csv_path)) and not args.force:
            print(f"error: {csv_path.name} already has scores; use --force to replace it.",
                  file=sys.stderr)
            return 2
        sample = sample_for_sheet(records, args.sample_size, args.seed, categories)
        sheet = sheet_path_for(questions_path)
        sheet.write_text(render_sheet(sample, items_by_id, chunk_texts, prompt,
                                      questions_path.name), encoding="utf-8")
        write_human_csv(csv_path, sample)
        print(f"Wrote {sheet} and {csv_path} ({len(sample)} items). Fill in the CSV, "
              "then run `make eval` to see judge-human agreement in the report.")
        return 0

    try:
        rp._read_api_key()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if JUDGE_MODEL == rp.GEN_MODEL or "latest" in JUDGE_MODEL:
        print(f"note: judge model '{JUDGE_MODEL}' should be a pinned version that differs "
              f"from the generator ('{rp.GEN_MODEL}'); see PLAN.md D4.")
    print(f"Judge: {JUDGE_MODEL}, prompt {prompt.name} ({prompt.sha})")

    judge_path = judge_path_for(questions_path)
    cache = load_json(judge_path)

    def _save(c):
        judge_path.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        stats = run_judge(records, items_by_id, chunk_texts, make_judge_fn(JUDGE_MODEL), cache,
                          prompt, JUDGE_MODEL, save_cache=_save, max_calls=args.max_calls,
                          sleep_between=args.sleep)
    except rp.GeminiUnavailableError as exc:
        print(f"\nStopped: {exc}\nJudgments so far are cached; run `make judge` again.",
              file=sys.stderr)
        return 3

    print(f"\nJudged {stats['judged']}/{stats['eligible']} eligible answers "
          f"({stats['new']} new, {stats['calls']} judge call(s)).")
    if stats["stop_reason"]:
        print(f"Stopped early: {stats['stop_reason']}")
    if stats["parse_errors"]:
        print(f"Unreadable judge replies (retried next run): {stats['parse_errors']}")
    if len(records) < total:
        print(f"Only {len(records)}/{total} questions have answers yet: run `make eval` "
              "to answer the rest, then `make judge` again.")
    if stats["remaining"]:
        print("Run `make judge` again later to judge the rest.")
        return 3
    print("All answered items are judged. Run `make eval` to rebuild the report "
          "(no new API calls once every question is answered).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
