"""
Offline tests for the judge-free evaluation metrics and report
(src/eval_metrics.py, src/eval_report.py) and for the harness running eval
set v2 (src/evaluate.py). No API key needed: answers are faked.
"""

import copy
import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import eval_metrics as em  # noqa: E402
from src import eval_report as er  # noqa: E402
from src import eval_set as es  # noqa: E402

IDK = "I don't know"
CHUNKS = {
    "doc_1": "Paramedical services: chiropractor, physiotherapy, massage therapist.",
    "doc_2": "Refer to your Schedule of Benefits for specific coverage amounts.",
    "doc_3": "Emergency travel: up to $5,000,000 per incident outside Canada.",
}
ANSWER_ITEM = {
    "id": "a1", "category": "direct_fact", "behavior": "answer",
    "question": "Is physio covered?", "expected_pages": [10, 11],
    "reference_answer": "Yes.", "expected_keywords": ["physiotherapy"],
    "evidence": [{"page": 10, "text": "chiropractor, physiotherapy"},
                 {"page": 17, "text": "$5,000,000 per incident"}],
}
DEFER_ITEM = {
    "id": "d1", "category": "deferred", "behavior": "defer",
    "question": "Drug maximum?", "expected_pages": [13],
    "reference_answer": "See your Schedule of Benefits.",
    "expected_keywords": ["Schedule of Benefits"],
    "evidence": [{"page": 13, "text": "Refer to your Schedule of Benefits"}],
}
ABSTAIN_ITEM = {"id": "x1", "category": "clear_oos", "behavior": "abstain",
                "question": "Capital of France?"}


def _rec(answer="Physiotherapy is covered.", pages=(10,), cited=("doc_1",),
         retrieved=("doc_1",), candidates=("doc_1", "doc_3"), verified=True, n_retrieved=None):
    abstained = answer == IDK
    return {
        "id": "?", "answer": answer, "abstained": abstained,
        "pages": [] if abstained else list(pages),
        "cited_ids": [] if abstained else list(cited),
        "retrieved_ids": list(retrieved), "retrieved_pages": [10] if retrieved else [],
        "n_retrieved": len(retrieved) if n_retrieved is None else n_retrieved,
        "candidates": [{"id": c, "page": 10, "distance": 0.3} for c in candidates],
        "citations_verified": None if abstained else verified,
        "nearest_distance": 0.3,
    }


def _score(rec, item):
    return em.score_record({**rec, "id": item["id"]}, item, CHUNKS)


# --- helpers -----------------------------------------------------------------------
def test_page_helpers_and_none_when_unspecified():
    assert em.page_hit([10], [10, 11]) is True and em.page_hit([3], [10]) is False
    assert em.page_hit([10], None) is None
    assert em.page_precision([10, 12], [10]) == 0.5
    assert em.page_precision([], [10]) is None and em.page_precision([10], []) is None
    assert em.rate(1, 0) is None and em.mean([None, None]) is None
    assert em.mean([True, False, None]) == 0.5


def test_evidence_matching_ignores_pdf_spacing():
    found = em.evidence_found([{"page": 1, "text": "31-day grace"}], ["a 31 -day  grace period"])
    assert found == [True]


# --- per-item scoring ---------------------------------------------------------------
def test_answer_item_passes_with_evidence_in_cited_chunk():
    r = _score(_rec(), ANSWER_ITEM)
    assert r["item_pass"] and r["behavior_correct"] and r["fail_reasons"] == []
    assert r["evidence_hit"] is True
    assert r["evidence_coverage"] == 0.5          # 1 of 2 phrases cited
    assert r["recall_at_k"] == 0.5                # doc_3 not retrieved...
    assert r["recall_at_k_pre_threshold"] == 1.0  # ...but it was in the top k
    assert r["cited_page_hit"] is True and r["cited_page_precision"] == 1.0
    assert r["keyword_pass"] is True


def test_citation_without_evidence_fails():
    r = _score(_rec(cited=("doc_3",), pages=(17,)), ANSWER_ITEM)
    assert r["evidence_hit"] is True  # doc_3 holds the second phrase
    r = _score(_rec(cited=("doc_2",), pages=(13,)), ANSWER_ITEM)
    assert r["evidence_hit"] is False and not r["item_pass"]
    assert r["cited_page_hit"] is False and r["cited_page_precision"] == 0.0
    assert r["fail_reasons"] == ["cited passages lack the evidence"]


def test_uncited_answer_counts_as_no_citation():
    # The pipeline falls back to all retrieved pages; that's not a citation.
    r = _score(_rec(cited=(), verified=False), ANSWER_ITEM)
    assert r["evidence_hit"] is False and r["cited_page_hit"] is False
    assert r["citation_page_hit"] is True  # legacy v1 metric keeps the fallback
    assert r["fail_reasons"] == ["cited no passage"]


def test_defer_needs_the_deferral_not_idk():
    ok = _score(_rec("Amounts are in your Schedule of Benefits.", pages=(13,),
                     cited=("doc_2",), retrieved=("doc_2",)), DEFER_ITEM)
    assert ok["item_pass"]

    idk = _score(_rec(IDK, retrieved=("doc_2",)), DEFER_ITEM)
    assert not idk["item_pass"] and idk["abstention_layer"] == "model"
    assert idk["fail_reasons"] == ["said \"I don't know\" (model)"]
    assert idk["evidence_hit"] is None  # citation metrics only for answered items

    vague = _score(_rec("Drugs are covered.", pages=(13,), cited=("doc_2",)), DEFER_ITEM)
    assert not vague["behavior_correct"]
    assert "no mention of the Schedule of Benefits" in vague["fail_reasons"]


def test_abstain_item():
    by_threshold = _score(_rec(IDK, retrieved=()), ABSTAIN_ITEM)
    assert by_threshold["item_pass"] and by_threshold["abstention_layer"] == "threshold"
    assert by_threshold["recall_at_k"] is None and by_threshold["keyword_pass"] is None
    answered = _score(_rec("Paris."), ABSTAIN_ITEM)
    assert not answered["item_pass"]
    assert answered["fail_reasons"] == ["answered, but should say \"I don't know\""]


def test_evidence_metrics_are_na_without_chunk_texts_or_evidence():
    r = em.score_record({**_rec(), "id": "a1"}, ANSWER_ITEM, None)
    assert r["evidence_hit"] is None and r["recall_at_k"] is None
    assert r["item_pass"]  # falls back to the cited page check
    v1_item = {"id": "in_01", "category": "in_scope", "behavior": "answer",
               "question": "q", "expected_pages": [99]}
    r = em.score_record({**_rec(), "id": "in_01"}, v1_item, CHUNKS)
    assert r["evidence_hit"] is None and not r["item_pass"]
    assert r["fail_reasons"] == ["cited a page outside expected_pages"]


# --- aggregation ---------------------------------------------------------------------
def _records():
    return [
        _score(_rec(), ANSWER_ITEM),                                    # pass
        _score(_rec(IDK, retrieved=()), {**ANSWER_ITEM, "id": "a2"}),   # wrongful abstention
        _score(_rec(IDK, retrieved=()), ABSTAIN_ITEM),                  # TP (threshold)
        _score(_rec(IDK), {**ABSTAIN_ITEM, "id": "x2"}),                # TP (model)
        _score(_rec("Paris."), {**ABSTAIN_ITEM, "id": "x3"}),           # FN
    ]


def test_abstention_precision_recall():
    a = em.abstention_confusion(_records())
    assert (a["tp"], a["fp"], a["fn"], a["tn"]) == (2, 1, 1, 1)
    assert a["precision"] == pytest.approx(2 / 3) and a["recall"] == pytest.approx(2 / 3)
    assert (a["tp_by_threshold"], a["tp_by_model"]) == (1, 1)
    assert a["fp_ids"] == ["a2"] and a["fn_ids"] == ["x3"]


def test_groups_and_empty_denominators():
    s = em.summarize_items(_records(), ["direct_fact", "deferred", "clear_oos"])
    assert list(s["by_category"]) == ["direct_fact", "clear_oos"]  # no empty groups
    assert list(s["by_behavior"]) == ["answer", "abstain"]
    oos = s["by_category"]["clear_oos"]
    assert oos["retrieval_hit_rate"] is None and oos["evidence_hit"] is None
    assert oos["wrongful_answers"] == 1 and oos["n_pass"] == 2
    assert s["overall"]["n_pass"] == 3 and s["overall"]["wrongful_abstentions"] == 1
    assert [f["id"] for f in s["failures"]] == ["a2", "x3"]
    empty = em.summarize_group([])
    assert empty["n"] == 0 and empty["pass_rate"] is None


# --- report ---------------------------------------------------------------------------
def test_report_renders_and_writes(tmp_path):
    ev = pytest.importorskip("src.evaluate")
    records = _records()
    summary = ev.summarize(records, ["direct_fact", "clear_oos"])
    meta = {"date": "2026-10-27", "eval_set": "eval/x.json", "eval_set_version": "v2.0",
            "n_items": len(records), "index": "app/demo_index", "n_chunks": 3,
            "gen_model": "m", "models_resolved": [], "embed_model": "e", "k": 4,
            "threshold": 0.37, "chunk_size": 800, "chunk_overlap": 128,
            "encoding": "cl100k_base", "git_commit": "abc123"}
    md = er.render_markdown(summary, records, meta)
    for heading in ("## Headline", "## By expected behaviour", "## By category",
                    "## Distance margin", "## Failures", "## All items"):
        assert heading in md
    for r in records:
        assert f"| {r['id']} |" in md
    md_path, json_path = er.write_report(tmp_path / "r" / "v2.0_x.md", summary, records, meta)
    assert md_path.exists() and json_path.exists()
    import json

    metrics = json.loads(json_path.read_text(encoding="utf-8"))
    assert metrics["failed_ids"] == ["a2", "x3"] and "Paris" not in json_path.read_text()


# --- v1 adapter ---------------------------------------------------------------------------
def test_v1_set_converts_to_items():
    v1 = es.load_eval_set(REPO_ROOT / "notebooks" / "eval" / "eval_questions.json")
    items = es.items_of(v1)
    assert es.is_v1(v1) and es.set_version(v1) == "v1" and len(items) == 18
    assert {(i["category"], i["behavior"]) for i in items} == {
        ("in_scope", "answer"), ("out_of_scope", "abstain")}
    v2 = es.load_eval_set(es.DEFAULT_SET)
    assert not es.is_v1(v2) and es.set_version(v2) == "v2.0" and len(es.items_of(v2)) == 65


# --- the harness on eval set v2 (fake answers, real demo-index chunks) ----------------------
@pytest.fixture(scope="module")
def demo_chunks(tmp_path_factory):
    pytest.importorskip("chromadb")
    from src import rag_pipeline as rp

    idx = tmp_path_factory.mktemp("idx") / "demo_index"  # Chroma rewrites files on open
    shutil.copytree(REPO_ROOT / "app" / "demo_index", idx)
    return es.chunks_from_collection(rp.load_persistent_collection(persist_dir=str(idx)))


def _perfect_answer_fn(v2, chunks):
    """Answers every item the way the eval set expects, citing the chunks that
    hold its evidence phrases."""
    by_q = {i["question"]: i for i in v2["items"]}

    def fn(question):
        item = by_q[question]
        if item["behavior"] == "abstain":
            return {"answer": IDK, "pages": [], "retrieved": [], "abstained": True,
                    "cited_ids": [], "citations_verified": False, "nearest_distance": 0.45,
                    "candidates": []}
        hits = [c for c in chunks if any(
            c["page"] == ev["page"]
            and es.normalize_text(ev["text"]) in es.normalize_text(c["text"])
            for ev in item["evidence"])]
        retrieved = [{"id": c["id"], "text": c["text"], "metadata": {"page": c["page"]},
                      "score": 0.3} for c in hits]
        return {"answer": item["reference_answer"], "retrieved": retrieved,
                "pages": sorted({c["page"] for c in hits}),
                "cited_ids": [c["id"] for c in hits], "citations_verified": True,
                "abstained": False, "nearest_distance": 0.3,
                "candidates": [{"id": c["id"], "page": c["page"], "distance": 0.3}
                               for c in hits]}
    return fn


def _run(v2, fn, chunks):
    from src import evaluate as ev

    texts = {c["id"]: c["text"] for c in chunks}
    return ev.run_eval(v2, fn, "idx", sleep_between=0, log=lambda _: None, chunk_texts=texts)


def test_v2_perfect_run_scores_100(demo_chunks):
    v2 = es.load_eval_set(es.DEFAULT_SET)
    records, s = _run(v2, _perfect_answer_fn(v2, demo_chunks), demo_chunks)
    assert len(records) == 65 and s["failures"] == []
    o, a = s["overall"], s["abstention"]
    assert o["pass_rate"] == 1.0 and o["evidence_hit"] == 1.0 and o["recall_at_k"] == 1.0
    assert o["evidence_coverage"] == 1.0 and o["cited_page_hit"] == 1.0
    assert a["precision"] == 1.0 and a["recall"] == 1.0 and a["tp"] == 18
    assert list(s["by_category"]) == list(v2["categories"])  # set order, all present


def test_v2_mistakes_show_up_in_the_right_places(demo_chunks):
    v2 = es.load_eval_set(es.DEFAULT_SET)
    perfect = _perfect_answer_fn(v2, demo_chunks)
    by_id = {i["id"]: i for i in v2["items"]}
    wrong_chunk = next(c for c in demo_chunks if c["page"] == 1)

    def fn(question):
        out = copy.deepcopy(perfect(question))
        qid = next(i for i, it in by_id.items() if it["question"] == question)
        if qid == "fact_01":     # threshold rejected a real question
            out.update(answer=IDK, abstained=True, retrieved=[], pages=[], cited_ids=[])
        elif qid == "defer_01":  # model refused instead of deferring
            out.update(answer=IDK, abstained=True, pages=[], cited_ids=[])
        elif qid == "oos_01":    # answered an unrelated question
            out.update(answer="Paris.", abstained=False, citations_verified=False)
        elif qid == "num_01":    # cited an unrelated passage
            out.update(cited_ids=[wrong_chunk["id"]], pages=[1])
        return out

    _, s = _run(v2, fn, demo_chunks)
    assert by_id["oos_01"]["category"] == "clear_oos"
    assert {f["id"] for f in s["failures"]} == {"fact_01", "defer_01", "num_01", "oos_01"}
    a = s["abstention"]
    assert a["fp_ids"] == ["fact_01", "defer_01"] and a["fn_ids"] == ["oos_01"]
    # 17 correct abstentions out of 19 abstentions, and out of 18 should-abstain items
    assert a["precision"] == pytest.approx(17 / 19) and a["recall"] == pytest.approx(17 / 18)
    cats = s["by_category"]
    assert cats["direct_fact"]["wrongful_abstentions"] == 1
    assert cats["deferred"]["n_pass"] == cats["deferred"]["n"] - 1
    assert cats["clear_oos"]["wrongful_answers"] == 1
    assert cats["numeric"]["evidence_hit"] < 1.0
    reasons = {f["id"]: f["reasons"] for f in s["failures"]}
    assert reasons["defer_01"] == ["said \"I don't know\" (model)"]
    assert reasons["fact_01"] == ["said \"I don't know\" (threshold)"]
    assert reasons["num_01"] == ["cited passages lack the evidence"]
