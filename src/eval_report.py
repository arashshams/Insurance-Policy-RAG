"""
eval_report.py — render an evaluation run as a markdown report + metrics JSON.

The report is what quality claims point to (PLAN.md decision D2): run config,
headline metrics, per-behaviour and per-category tables, the distance margin,
every failure with its reason, and a per-item table that diffs cleanly between
runs. The JSON holds the same metrics (no answers) for tracking over time.
"""

from __future__ import annotations

import json
from pathlib import Path

ANSWER_EXCERPT_CHARS = 160


def pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def num(x) -> str:
    return "n/a" if x is None else f"{x:.3f}"


def _cell(text) -> str:
    return str("" if text is None else text).replace("|", "\\|").replace("\n", " ").strip()


def _excerpt(text: str, n: int = ANSWER_EXCERPT_CHARS) -> str:
    t = " ".join((text or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def _outcome(rec: dict) -> str:
    if rec.get("abstained"):
        return f"I don't know ({rec.get('abstention_layer')})"
    return "answered"


def _group_table(groups: dict, label: str) -> list[str]:
    rows = [
        f"| {label} | Items | Pass | Wrongful abstain | Wrongful answer | Recall@k "
        "| Cited page hit | Evidence hit | Keywords |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, g in groups.items():
        rows.append(
            f"| {name} | {g['n']} | {g['n_pass']}/{g['n']} ({pct(g['pass_rate'])}) "
            f"| {g['wrongful_abstentions']}/{g['n_should_answer']} "
            f"| {g['wrongful_answers']}/{g['n_should_abstain']} "
            f"| {pct(g['recall_at_k'])} | {pct(g['cited_page_hit'])} "
            f"| {pct(g['evidence_hit'])} | {pct(g['keyword_rate'])} |"
        )
    return rows


def _num2(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def _judge_section(j: dict) -> list[str]:
    g = j["overall"]
    complete = g["n_judged"] == g["n_eligible"]
    out = [
        "## LLM judge",
        "",
        f"Judge `{j['model']}` with prompt `{j['prompt']}` ({j['prompt_sha']}), scoring "
        "answered items that showed the right behaviour, on a 0–2 scale: *faithfulness* "
        "(every claim supported by the retrieved passages) and *correctness* (matches the "
        "reference answer). Rubric: `eval/prompts/" + j["prompt"] + ".md`.",
        "",
    ]
    if not complete:
        out += [f"**Not final:** {g['n_judged']} of {g['n_eligible']} eligible answers are "
                "judged so far (`make judge` continues).", ""]
    out += [
        "| Metric | Result |",
        "|---|---|",
        f"| Judged | {g['n_judged']} / {g['n_eligible']} |",
        f"| Fully correct (2) | {pct(g['fully_correct'])} |",
        f"| Fully faithful (2) | {pct(g['fully_faithful'])} |",
        f"| Hallucination rate (faithfulness 0) | {pct(g['hallucination_rate'])} |",
        f"| Mean correctness / faithfulness | {_num2(g['mean_correctness'])} / "
        f"{_num2(g['mean_faithfulness'])} |",
        f"| Strict pass (pass + both scores 2), all items | "
        f"{pct(g['strict_pass_rate']) if g['strict_pass_rate'] is not None else 'n/a until fully judged'} |",
        "",
        "| Category | Judged | Fully correct | Fully faithful | Hallucination |",
        "|---|---|---|---|---|",
    ]
    for cat, c in j["by_category"].items():
        out.append(f"| {cat} | {c['n_judged']}/{c['n_eligible']} | {pct(c['fully_correct'])} "
                   f"| {pct(c['fully_faithful'])} | {pct(c['hallucination_rate'])} |")
    a = j.get("agreement")
    out += ["", "### Judge vs human", ""]
    if not a:
        out.append("No human scores yet (`make judge-sheet`, then fill in the CSV).")
    elif not a.get("dims"):
        out.append("Human scores exist, but none of their answers are judged yet "
                   "(or they were given for older answers).")
    else:
        out += ["| Score | Items | Exact agreement | Within one | Weighted kappa "
                "| Judge mean | Human mean |", "|---|---|---|---|---|---|---|"]
        for dim, d in a["dims"].items():
            out.append(f"| {dim} | {d['n']} | {pct(d['exact'])} | {pct(d['within_one'])} "
                       f"| {_num2(d['weighted_kappa'])} | {_num2(d['judge_mean'])} "
                       f"| {_num2(d['human_mean'])} |")
    if a and a.get("stale_ids"):
        out += ["", f"Human scores for an older answer (not counted): {', '.join(a['stale_ids'])}."]
    out += ["", "### Answers below full marks", ""]
    if not j["below_full"]:
        out.append("None." if complete else "None so far.")
    else:
        out += ["| ID | Category | Correctness | Faithfulness | Judge's reason "
                "| Unsupported claims |", "|---|---|---|---|---|---|"]
        for b in j["below_full"]:
            out.append(f"| {b['id']} | {b['category']} | {b['correctness']} | {b['faithfulness']} "
                       f"| {_cell(b['reason'])} | {_cell('; '.join(b['unsupported_claims']))} |")
    return out + [""]


def render_markdown(summary: dict, records: list[dict], meta: dict) -> str:
    o = summary["overall"]
    a = summary["abstention"]
    m = summary["distance_margin"]
    resolved = ", ".join(meta.get("models_resolved") or []) or "not reported"
    out = [
        f"# Evaluation report — eval set {meta['eval_set_version']}, {meta['date']}",
        "",
        "Generated by `python -m src.evaluate` (`make eval`). Judge-free metrics: "
        "abstention, retrieval and citation checks against the eval set's expected "
        "pages and evidence phrases. Answer correctness is not judged here.",
        "",
        "## Run",
        "",
        "| Setting | Value |",
        "|---|---|",
        f"| Eval set | `{_cell(meta['eval_set'])}` ({meta['n_items']} items) |",
        f"| Index | `{_cell(meta['index'])}` ({meta['n_chunks']} chunks) |",
        f"| Generation model | `{meta['gen_model']}` (API reported: {_cell(resolved)}) |",
        f"| Embedding model | `{meta['embed_model']}` |",
        f"| Retrieval | k = {meta['k']}, distance threshold = {meta['threshold']} |",
        f"| Chunking | {meta['chunk_size']} tokens, overlap {meta['chunk_overlap']}, "
        f"`{meta['encoding']}` |",
        f"| Code | {_cell(meta.get('git_commit') or 'unknown')} |",
        "",
        "## Headline",
        "",
        "| Metric | Result |",
        "|---|---|",
        f"| Items passed | **{o['n_pass']} / {o['n']}** ({pct(o['pass_rate'])}) |",
        f"| Correct behaviour (answer / defer / abstain) | {pct(o['behavior_accuracy'])} |",
        f"| Abstention precision | {pct(a['precision'])} ({a['tp']} of {a['tp'] + a['fp']} "
        "abstentions were meant to abstain) |",
        f"| Abstention recall | {pct(a['recall'])} ({a['tp']} of {a['tp'] + a['fn']} "
        "should-abstain items abstained) |",
        f"| Correct abstentions: by threshold / by model | {a['tp_by_threshold']} / "
        f"{a['tp_by_model']} |",
        f"| Retrieval hit rate (answer + defer) | {pct(o['retrieval_hit_rate'])} |",
        f"| Page hit@k (after threshold) | {pct(o['page_hit_at_k'])} |",
        f"| Recall@k, after / before threshold | {pct(o['recall_at_k'])} / "
        f"{pct(o['recall_at_k_pre_threshold'])} |",
        f"| Cited page hit / precision (of answered) | {pct(o['cited_page_hit'])} / "
        f"{pct(o['cited_page_precision'])} |",
        f"| Citation evidence hit (of answered) | {pct(o['evidence_hit'])} |",
        f"| Evidence coverage (of answered) | {pct(o['evidence_coverage'])} |",
        f"| Keyword rate (of answered) | {pct(o['keyword_rate'])} |",
        "",
        "Definitions: *abstention* is the exact \"I don't know\" reply, with "
        "\"should abstain\" as the positive class. *Page hit@k*: a chunk on one of the "
        "item's expected pages was retrieved. *Recall@k*: the share of the item's "
        "evidence phrases contained in the retrieved chunks. *Cited page hit*: the "
        "answer cited a passage on an expected page. *Evidence hit*: a cited passage "
        "contains one of the item's evidence phrases from the policy (*coverage*: the "
        "share of its phrases found). *Pass*: correct behaviour, plus an evidence hit "
        "for answer and defer items. A *defer* item must mention the Schedule of "
        "Benefits rather than say \"I don't know\".",
        "",
        "## By expected behaviour",
        "",
        *_group_table(summary["by_behavior"], "Behaviour"),
        "",
        "## By category",
        "",
        *_group_table(summary["by_category"], "Category"),
        "",
        *(_judge_section(summary["judge"]) if summary.get("judge") else []),
        "## Distance margin",
        "",
        "Closest-passage cosine distance *before* the threshold (lower = closer).",
        "",
        "| Expected behaviour | Items | Min | Median | Max |",
        "|---|---|---|---|---|",
    ]
    for b, d in summary["distance_by_behavior"].items():
        out.append(f"| {b} | {d['n']} | {num(d['min'])} | {num(d['median'])} | {num(d['max'])} |")
    out.append("")
    if m["separable"]:
        out.append(f"Answer/defer max {num(m['in_scope_max'])} < abstain min "
                   f"{num(m['out_of_scope_min'])}: separable; midpoint "
                   f"{m['suggested_threshold']} (current {meta['threshold']}).")
    elif m["separable"] is False:
        out.append(f"Answer/defer max {num(m['in_scope_max'])} ≥ abstain min "
                   f"{num(m['out_of_scope_min'])}: the sets overlap, so the threshold alone "
                   "cannot separate them; the model's refusal handles the rest.")
    out += ["", "## Failures", ""]
    failed = [r for r in records if not r["item_pass"]]
    if not failed:
        out.append("None.")
    else:
        out += ["| ID | Category | Expected | Got | Nearest | Reason | Answer (excerpt) |",
                "|---|---|---|---|---|---|---|"]
        for r in failed:
            out.append(
                f"| {r['id']} | {r['category']} | {r['behavior']} | {_cell(_outcome(r))} "
                f"| {num(r.get('nearest_distance'))} | {_cell('; '.join(r['fail_reasons']))} "
                f"| {_cell(_excerpt(r.get('answer', '')))} |"
            )
    out += [
        "",
        "## All items",
        "",
        "| ID | Category | Expected | Got | Pass | Nearest | Recall@k | Cited pages "
        "| Evidence |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        if r.get("abstained"):
            cited = "—"
        elif r.get("citations_verified") is False:
            cited = "none"
        else:
            cited = ", ".join(str(p) for p in (r.get("pages") or []))
        ev = "n/a" if r.get("evidence_coverage") is None else pct(r["evidence_coverage"])
        out.append(
            f"| {r['id']} | {r['category']} | {r['behavior']} | {_cell(_outcome(r))} "
            f"| {'yes' if r['item_pass'] else '**no**'} | {num(r.get('nearest_distance'))} "
            f"| {pct(r.get('recall_at_k'))} | {cited or '—'} | {ev} |"
        )
    return "\n".join(out) + "\n"


def metrics_json(summary: dict, meta: dict) -> dict:
    """Metrics only (no answers or question text), for tracking runs over time."""
    keep = ("overall", "abstention", "by_behavior", "by_category", "distance_by_behavior",
            "distance_margin", "models_resolved", "judge")
    return {
        "meta": meta,
        **{k: summary[k] for k in keep if k in summary},
        "failed_ids": [f["id"] for f in summary.get("failures") or []],
    }


def write_report(md_path: str | Path, summary: dict, records: list[dict],
                 meta: dict) -> tuple[Path, Path]:
    md_path = Path(md_path)
    json_path = md_path.with_suffix(".json")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(render_markdown(summary, records, meta), encoding="utf-8")
    json_path.write_text(json.dumps(metrics_json(summary, meta), indent=2) + "\n",
                         encoding="utf-8")
    return md_path, json_path
