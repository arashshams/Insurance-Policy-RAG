"""
eval_set.py — load, validate and render versioned evaluation sets (eval/).

An eval set (e.g. eval/questions_v2.json) is the ground truth for every quality
claim, so it is checked like code:

  * validate_eval_set()    schema checks: unique ids, known categories and
                           behaviours, required fields per behaviour.
  * check_evidence()       every evidence phrase appears on its stated page of
                           an index (tests run it against app/demo_index).
  * check_evidence_in_chunks()  ...and inside a single chunk of that page, so
                           the harness can find it in a cited chunk.
  * items_of()             any set (v1 or v2) as v2-shaped items, for the harness.
  * render_review_markdown() a human-readable table for reviewing the set in a
                           PR, committed as eval/questions_v2_review.md.

CLI (from the repo root):
    python -m src.eval_set                      # validate + rewrite the review file
    python -m src.eval_set --check              # validate; fail if review file is stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SET = REPO_ROOT / "eval" / "questions_v2.json"

BEHAVIORS_NEEDING_GROUND_TRUTH = ("answer", "defer")


# --- loading / validation ----------------------------------------------------
def load_eval_set(path: str | Path = DEFAULT_SET) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def is_v1(data: dict) -> bool:
    """v1 sets (notebooks/eval/eval_questions.json) have in_scope/out_of_scope
    lists instead of a single `items` list."""
    return "items" not in data and ("in_scope" in data or "out_of_scope" in data)


def set_version(data: dict) -> str:
    """Version label for reports: "v2.0" for eval/questions_v2.json, "v1" for v1."""
    if is_v1(data):
        return "v1"
    v = str(data.get("version") or "unversioned")
    return v if v.startswith("v") else f"v{v}"


def items_of(data: dict) -> list[dict]:
    """The questions of any eval set as v2-shaped items, so the harness has ONE
    scoring path. v1 in-scope questions become behavior "answer" and
    out-of-scope ones "abstain"; their category stays "in_scope" /
    "out_of_scope". v1 has no reference answers or evidence phrases, so the
    evidence-based metrics are simply n/a for it."""
    if not is_v1(data):
        return list(data.get("items") or [])
    items = []
    for category, behavior in (("in_scope", "answer"), ("out_of_scope", "abstain")):
        for q in data.get(category) or []:
            items.append({**q, "category": category, "behavior": behavior})
    return items


def validate_eval_set(data: dict) -> list[str]:
    """Return a list of problems (empty = valid)."""
    problems: list[str] = []
    for key in ("version", "idk_answer", "behaviors", "categories", "items"):
        if key not in data:
            problems.append(f"missing top-level key '{key}'")
    if problems:
        return problems

    seen: set[str] = set()
    for i, item in enumerate(data["items"]):
        qid = item.get("id") or f"<item {i}>"
        if not item.get("id"):
            problems.append(f"{qid}: missing id")
        elif qid in seen:
            problems.append(f"{qid}: duplicate id")
        seen.add(qid)
        if not (item.get("question") or "").strip():
            problems.append(f"{qid}: empty question")
        if item.get("category") not in data["categories"]:
            problems.append(f"{qid}: unknown category {item.get('category')!r}")
        behavior = item.get("behavior")
        if behavior not in data["behaviors"]:
            problems.append(f"{qid}: unknown behavior {behavior!r}")
            continue

        if behavior in BEHAVIORS_NEEDING_GROUND_TRUTH:
            pages = item.get("expected_pages") or []
            if not pages or not all(isinstance(p, int) and p > 0 for p in pages):
                problems.append(f"{qid}: needs expected_pages (positive ints)")
            if not (item.get("reference_answer") or "").strip():
                problems.append(f"{qid}: needs a reference_answer")
            evidence = item.get("evidence") or []
            if not evidence:
                problems.append(f"{qid}: needs at least one evidence phrase")
            for ev in evidence:
                if ev.get("page") not in pages:
                    problems.append(f"{qid}: evidence page {ev.get('page')} not in expected_pages")
                if not (ev.get("text") or "").strip():
                    problems.append(f"{qid}: empty evidence text")
        else:  # abstain: nothing in the policy should support an answer
            for key in ("expected_pages", "reference_answer", "evidence", "expected_keywords"):
                if item.get(key):
                    problems.append(f"{qid}: abstain items must not have '{key}'")
    return problems


# --- evidence check against an index -------------------------------------------
def normalize_text(text: str) -> str:
    """Lowercase alphanumerics only. PDF extraction inserts stray spaces
    ('31 -day', 'h ospitalization') and curly quotes; this makes evidence
    phrases match regardless."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def page_texts_from_collection(collection) -> dict[int, str]:
    """Concatenated, normalized text per page from a Chroma collection."""
    got = collection.get(include=["documents", "metadatas"])
    pages: dict[int, str] = defaultdict(str)
    for doc, meta in zip(got["documents"], got["metadatas"]):
        page = (meta or {}).get("page")
        if page is not None:
            pages[int(page)] += normalize_text(doc)
    return dict(pages)


def check_evidence(data: dict, page_texts: dict[int, str]) -> list[str]:
    """Problems where an evidence phrase is not found on its stated page."""
    problems = []
    for item in data["items"]:
        for ev in item.get("evidence") or []:
            if normalize_text(ev["text"]) not in page_texts.get(ev["page"], ""):
                problems.append(f"{item['id']}: evidence not found on page {ev['page']}: "
                                f"{ev['text'][:60]!r}")
        for p in item.get("expected_pages") or []:
            if p not in page_texts:
                problems.append(f"{item['id']}: expected page {p} not in the index")
    return problems


def chunks_from_collection(collection) -> list[dict]:
    """Every chunk of a Chroma collection as {"id", "page", "text"}."""
    got = collection.get(include=["documents", "metadatas"])
    return [
        {"id": _id, "page": (meta or {}).get("page"), "text": doc or ""}
        for _id, doc, meta in zip(got["ids"], got["documents"], got["metadatas"])
    ]


def check_evidence_in_chunks(data: dict, chunks: list[dict]) -> list[str]:
    """Problems where an evidence phrase is not inside ONE chunk of its page.

    The harness checks citations by looking for evidence phrases in the text of
    the chunks an answer cited. A phrase split across two chunks could never be
    found that way, so it would count every correct citation as a miss. Fix by
    shortening the phrase to the part inside one chunk."""
    by_page: dict[int, list[str]] = defaultdict(list)
    for c in chunks:
        if c.get("page") is not None:
            by_page[int(c["page"])].append(normalize_text(c["text"]))
    problems = []
    for item in data["items"]:
        for ev in item.get("evidence") or []:
            phrase = normalize_text(ev["text"])
            if not any(phrase in t for t in by_page.get(ev["page"], [])):
                problems.append(f"{item['id']}: evidence on page {ev['page']} is not inside "
                                f"a single chunk: {ev['text'][:60]!r}")
    return problems


# --- review rendering ------------------------------------------------------------
def _cell(text) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ")


def review_path_for(set_path: str | Path) -> Path:
    p = Path(set_path)
    return p.with_name(p.stem + "_review.md")


def render_review_markdown(data: dict, set_name: str) -> str:
    items = data["items"]
    cats = Counter(i["category"] for i in items)
    behs = Counter(i["behavior"] for i in items)
    out = [
        f"# Eval set {data['version']} — review table",
        "",
        f"Generated from `eval/{set_name}` by `python -m src.eval_set`. "
        "Do not edit by hand; edit the JSON and regenerate.",
        "",
        f"Source document: {data.get('source_document', 'n/a')}. "
        f"{len(items)} questions: "
        + ", ".join(f"{n} {b}" for b, n in sorted(behs.items())) + ".",
        "",
        "## Behaviours",
        "",
    ]
    out += [f"- **{b}**: {desc}" for b, desc in data["behaviors"].items()]
    out += ["", "## Categories", "", "| Category | Count | Meaning |", "|---|---|---|"]
    out += [f"| {c} | {cats.get(c, 0)} | {_cell(desc)} |" for c, desc in data["categories"].items()]

    for cat in data["categories"]:
        rows = [i for i in items if i["category"] == cat]
        if not rows:
            continue
        out += ["", f"## {cat} ({len(rows)})", "",
                "| ID | Question | Expect | Pages | Reference answer | Evidence (page: phrase) | Notes |",
                "|---|---|---|---|---|---|---|"]
        for i in rows:
            qid = i["id"] + (f" (v1 {i['v1_id']})" if i.get("v1_id") else "")
            pages = ", ".join(str(p) for p in i.get("expected_pages") or []) or "—"
            evidence = "<br>".join(f"p.{e['page']}: “{_cell(e['text'])}”"
                                   for e in i.get("evidence") or []) or "—"
            ref = i.get("reference_answer") or ('"' + data["idk_answer"] + '"')
            out.append(f"| {qid} | {_cell(i['question'])} | {i['behavior']} | {pages} | "
                       f"{_cell(ref)} | {evidence} | {_cell(i.get('notes'))} |")
    return "\n".join(out) + "\n"


# --- CLI ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate an eval set and render its review table.")
    ap.add_argument("path", nargs="?", default=str(DEFAULT_SET))
    ap.add_argument("--check", action="store_true",
                    help="don't write; fail if the review file is missing or stale")
    args = ap.parse_args(argv)

    path = Path(args.path)
    data = load_eval_set(path)
    problems = validate_eval_set(data)
    if problems:
        print("Eval set problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1

    review = render_review_markdown(data, path.name)
    review_path = review_path_for(path)
    if args.check:
        current = review_path.read_text(encoding="utf-8") if review_path.exists() else None
        if current != review:
            print(f"{review_path.name} is stale; run: python -m src.eval_set", file=sys.stderr)
            return 1
        print(f"OK: {path.name} is valid and {review_path.name} is up to date.")
        return 0
    review_path.write_text(review, encoding="utf-8")
    print(f"OK: {path.name} is valid ({len(data['items'])} items); wrote {review_path.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
