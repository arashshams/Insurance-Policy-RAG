"""
eval_metrics.py — judge-free scoring for the evaluation harness.

Pure functions, no API calls: src/evaluate.py runs the questions and stores
what the pipeline returned; this module turns those records into metrics.
Scoring is always re-applied from the CURRENT eval set, so fixing a question's
expected pages, keywords or evidence never needs new API calls.

Every item is scored by its expected `behavior` (eval/questions_v2.json):
  answer   answer from the policy, citing a passage that holds the evidence
  defer    say the detail is in the Schedule of Benefits and cite that passage;
           "I don't know" is wrong (PLAN.md decision D8)
  abstain  reply exactly "I don't know"

Metrics (definitions also in the report):
  * Abstention precision / recall, positive class = "should abstain".
  * Retrieval: hit rate (a chunk passed the threshold), page hit@k (a chunk
    on one of expected_pages was retrieved), and recall@k = share of the
    item's evidence phrases contained in the retrieved chunks, after the
    threshold (what the model saw) and before it (the raw top k).
    Recall is measured on evidence, not on expected_pages, because
    expected_pages lists ACCEPTABLE pages (any one of them may hold the
    answer), while every evidence phrase is text the answer needs.
  * Citations (of answered items): cited pages that are expected (hit and
    precision), and the stricter evidence check: an evidence phrase from the
    policy appears in a chunk the answer cited (evidence hit), and the share
    of an item's evidence phrases covered by its cited chunks (coverage).
  * Keyword rate: all expected_keywords appear in the answer (kept from v1).
  * Item pass: correct behaviour, and for answer/defer items an evidence hit
    (v1 items have no evidence, so a citation page hit stands in).
Whether an answer's content is right is NOT judged here; that is the LLM
judge's job (M1c).
"""

from __future__ import annotations

from src.eval_set import normalize_text

SHOULD_ANSWER = ("answer", "defer")
DEFERRAL_PHRASE = "Schedule of Benefits"


# --- small helpers -------------------------------------------------------------
def rate(n: int, d: int) -> float | None:
    return (n / d) if d else None


def mean(values) -> float | None:
    """Mean of the non-None values (bools count as 0/1); None if there are none."""
    vals = [float(v) for v in values if v is not None]
    return (sum(vals) / len(vals)) if vals else None


def contains_keywords(answer: str, keywords: list[str] | None) -> bool | None:
    """True if every expected keyword appears in the answer (case-insensitive).
    None if no real keywords are set (missing, or the "TODO" placeholder)."""
    kws = [k for k in (keywords or []) if k and k != "TODO"]
    if not kws:
        return None
    a = (answer or "").lower()
    return all(k.lower() in a for k in kws)


def page_hit(pages, expected_pages) -> bool | None:
    """True if any expected page is in `pages`; None if none are specified."""
    if not expected_pages:
        return None
    return bool(set(pages or []) & set(expected_pages))


def page_precision(pages, expected_pages) -> float | None:
    """Share of `pages` that are expected; None if no pages or no expectation."""
    if not expected_pages or not pages:
        return None
    pages = set(pages)
    return len(pages & set(expected_pages)) / len(pages)


def mentions_deferral(answer: str) -> bool:
    return normalize_text(DEFERRAL_PHRASE) in normalize_text(answer)


def evidence_found(evidence: list[dict], texts: list[str]) -> list[bool]:
    """For each evidence phrase, whether it appears in any of `texts`
    (normalized the same way the eval-set validator normalizes them)."""
    norm = [normalize_text(t) for t in texts]
    return [any(normalize_text(ev["text"]) in t for t in norm) for ev in evidence]


def cited_pages(rec: dict) -> list:
    """Pages of the passages the answer actually cited. The pipeline falls back
    to all retrieved pages when the model cited nothing (citations_verified
    False); that fallback is not a citation, so it counts as none here.
    Legacy records with unknown verification (None) use `pages` as is."""
    if rec.get("abstained") or rec.get("citations_verified") is False:
        return []
    return list(rec.get("pages") or [])


def abstention_layer(rec: dict) -> str | None:
    """How an abstention happened: "threshold" (no chunk passed, no LLM call)
    or "model" (chunks passed but the model said "I don't know")."""
    if not rec.get("abstained"):
        return None
    return "threshold" if rec.get("n_retrieved", 0) == 0 else "model"


# --- per-item scoring ------------------------------------------------------------
def score_record(rec: dict, item: dict, chunk_texts: dict[str, str] | None = None) -> dict:
    """(Re)compute every scoring field of a record from the CURRENT item.

    `chunk_texts` maps chunk id -> text for the index that was evaluated; it is
    needed only for the evidence metrics (None -> they are n/a). Records never
    store chunk text, so a cache of a private policy's run holds no policy text.
    """
    behavior = item["behavior"]
    rec["behavior"] = behavior
    rec["category"] = item["category"]
    expected_pages = item.get("expected_pages")
    evidence = item.get("evidence") or []
    abstained = bool(rec.get("abstained"))
    answered = not abstained
    should_answer = behavior in SHOULD_ANSWER

    cpages = cited_pages(rec)

    def _texts(ids) -> list[str]:
        return [chunk_texts[i] for i in ids if i in chunk_texts]

    def _evidence_recall(ids) -> float | None:
        if not (should_answer and evidence) or chunk_texts is None or ids is None:
            return None
        found = evidence_found(evidence, _texts(ids))
        return sum(found) / len(found)

    # Legacy v1 fields (keep v1 summaries comparable with earlier runs).
    rec["keyword_pass"] = (contains_keywords(rec.get("answer", ""), item.get("expected_keywords"))
                           if should_answer else None)
    rec["retrieval_page_hit"] = (page_hit(rec.get("retrieved_pages"), expected_pages)
                                 if should_answer else None)
    rec["citation_page_hit"] = (
        None if not (should_answer and expected_pages)
        else (False if abstained else page_hit(rec.get("pages"), expected_pages))
    )

    # Retrieval.
    rec["recall_at_k"] = _evidence_recall(rec.get("retrieved_ids"))
    candidates = rec.get("candidates")
    rec["recall_at_k_pre_threshold"] = _evidence_recall(
        None if candidates is None else [c.get("id") for c in candidates])

    # Citations: only meaningful for answered answer/defer items.
    cite_scope = should_answer and answered
    rec["cited_page_hit"] = page_hit(cpages, expected_pages) if cite_scope else None
    rec["cited_page_precision"] = (
        (page_precision(cpages, expected_pages) if cpages else 0.0)
        if cite_scope and expected_pages else None
    )
    if cite_scope and evidence and chunk_texts is not None:
        cited = [] if rec.get("citations_verified") is False else (rec.get("cited_ids") or [])
        found = evidence_found(evidence, _texts(cited))
        rec["evidence_hit"] = any(found)
        rec["evidence_coverage"] = sum(found) / len(found)
    else:
        rec["evidence_hit"] = None
        rec["evidence_coverage"] = None

    # Behaviour.
    if behavior == "abstain":
        correct = abstained
    elif behavior == "defer":
        correct = answered and mentions_deferral(rec.get("answer", ""))
    else:
        correct = answered
    rec["behavior_correct"] = correct
    rec["abstention_layer"] = abstention_layer(rec)

    # Grounding check for the pass/fail verdict.
    if not should_answer or not correct:
        grounded = True
    elif rec["evidence_hit"] is not None:
        grounded = rec["evidence_hit"]
    elif rec["cited_page_hit"] is not None:
        grounded = rec["cited_page_hit"]
    else:
        grounded = True
    rec["item_pass"] = bool(correct and grounded)
    rec["fail_reasons"] = failure_reasons(rec)
    return rec


def failure_reasons(rec: dict) -> list[str]:
    """Short, human-readable reasons an item failed (empty if it passed)."""
    if rec.get("item_pass"):
        return []
    reasons = []
    behavior = rec["behavior"]
    if behavior == "abstain":
        reasons.append("answered, but should say \"I don't know\"")
        return reasons
    if rec.get("abstained"):
        reasons.append(f"said \"I don't know\" ({rec.get('abstention_layer')})")
        return reasons
    if behavior == "defer" and not mentions_deferral(rec.get("answer", "")):
        reasons.append("no mention of the Schedule of Benefits")
    if rec.get("citations_verified") is False:
        reasons.append("cited no passage")
    elif rec.get("evidence_hit") is False:
        reasons.append("cited passages lack the evidence")
    elif rec.get("evidence_hit") is None and rec.get("cited_page_hit") is False:
        reasons.append("cited a page outside expected_pages")
    return reasons or ["failed"]


# --- aggregation ---------------------------------------------------------------------
def abstention_confusion(records: list[dict]) -> dict:
    """Abstention as a binary classifier; positive class = "should abstain"."""
    tp = [r for r in records if r["behavior"] == "abstain" and r["abstained"]]
    fn = [r for r in records if r["behavior"] == "abstain" and not r["abstained"]]
    fp = [r for r in records if r["behavior"] in SHOULD_ANSWER and r["abstained"]]
    tn = [r for r in records if r["behavior"] in SHOULD_ANSWER and not r["abstained"]]
    return {
        "tp": len(tp), "fp": len(fp), "fn": len(fn), "tn": len(tn),
        "precision": rate(len(tp), len(tp) + len(fp)),
        "recall": rate(len(tp), len(tp) + len(fn)),
        "tp_by_threshold": sum(r["abstention_layer"] == "threshold" for r in tp),
        "tp_by_model": sum(r["abstention_layer"] == "model" for r in tp),
        "fp_ids": [r["id"] for r in fp],
        "fn_ids": [r["id"] for r in fn],
    }


def summarize_group(records: list[dict]) -> dict:
    """Metrics for any subset of records (overall, one behaviour, one category)."""
    should = [r for r in records if r["behavior"] in SHOULD_ANSWER]
    answered = [r for r in should if not r["abstained"]]
    abstain = [r for r in records if r["behavior"] == "abstain"]
    return {
        "n": len(records),
        "pass_rate": rate(sum(r["item_pass"] for r in records), len(records)),
        "n_pass": sum(r["item_pass"] for r in records),
        "behavior_accuracy": rate(sum(r["behavior_correct"] for r in records), len(records)),
        "n_should_answer": len(should),
        "n_answered": len(answered),
        "n_should_abstain": len(abstain),
        "n_abstained_correctly": sum(r["abstained"] for r in abstain),
        "wrongful_abstentions": len(should) - len(answered),
        "wrongful_answers": sum(not r["abstained"] for r in abstain),
        "retrieval_hit_rate": rate(sum(r.get("n_retrieved", 0) > 0 for r in should), len(should)),
        "page_hit_at_k": mean(r.get("retrieval_page_hit") for r in should),
        "recall_at_k": mean(r.get("recall_at_k") for r in should),
        "recall_at_k_pre_threshold": mean(r.get("recall_at_k_pre_threshold") for r in should),
        "cited_page_hit": mean(r.get("cited_page_hit") for r in answered),
        "cited_page_precision": mean(r.get("cited_page_precision") for r in answered),
        "evidence_hit": mean(r.get("evidence_hit") for r in answered),
        "evidence_coverage": mean(r.get("evidence_coverage") for r in answered),
        "keyword_rate": mean(r.get("keyword_pass") for r in answered),
    }


def distance_by_behavior(records: list[dict]) -> dict:
    """Closest-passage distance (before the threshold) per behaviour."""
    out = {}
    for b in sorted({r["behavior"] for r in records}):
        d = sorted(r["nearest_distance"] for r in records
                   if r["behavior"] == b and r.get("nearest_distance") is not None)
        out[b] = ({"n": len(d), "min": d[0], "median": d[len(d) // 2], "max": d[-1]}
                  if d else {"n": 0, "min": None, "median": None, "max": None})
    return out


def summarize_items(records: list[dict], category_order: list[str] | None = None) -> dict:
    """Overall, per-behaviour and per-category metrics plus the failure list."""
    cats = list(category_order or [])
    cats += sorted({r["category"] for r in records} - set(cats))
    behaviors = [b for b in ("answer", "defer", "abstain") if any(r["behavior"] == b for r in records)]
    return {
        "overall": summarize_group(records),
        "abstention": abstention_confusion(records),
        "by_behavior": {b: summarize_group([r for r in records if r["behavior"] == b])
                        for b in behaviors},
        "by_category": {c: summarize_group([r for r in records if r["category"] == c])
                        for c in cats if any(r["category"] == c for r in records)},
        "distance_by_behavior": distance_by_behavior(records),
        "failures": [
            {"id": r["id"], "category": r["category"], "behavior": r["behavior"],
             "reasons": r["fail_reasons"], "nearest_distance": r.get("nearest_distance")}
            for r in records if not r["item_pass"]
        ],
    }
