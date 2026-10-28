"""
Offline tests for the LLM judge (src/judge.py) and its place in the report.
No API key needed: the judge model is replaced by a fake.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("openai")

from src import eval_metrics as em  # noqa: E402
from src import eval_report as er  # noqa: E402
from src import judge as jd  # noqa: E402
from src import rag_pipeline as rp  # noqa: E402

CHUNKS = {"doc_1": "Physiotherapy is covered under paramedical services.",
          "doc_2": "Refer to your Schedule of Benefits for specific coverage amounts."}
ITEMS = {
    "a1": {"id": "a1", "category": "direct_fact", "behavior": "answer",
           "question": "Is physio covered?", "expected_pages": [10],
           "reference_answer": "Yes, under paramedical services.",
           "evidence": [{"page": 10, "text": "Physiotherapy is covered"}]},
    "a2": {"id": "a2", "category": "numeric", "behavior": "answer",
           "question": "Physio limit?", "expected_pages": [10],
           "reference_answer": "Covered under paramedical services.",
           "evidence": [{"page": 10, "text": "paramedical services"}]},
    "d1": {"id": "d1", "category": "deferred", "behavior": "defer",
           "question": "Drug maximum?", "expected_pages": [13],
           "reference_answer": "It is in your Schedule of Benefits.",
           "evidence": [{"page": 13, "text": "Refer to your Schedule of Benefits"}]},
    "x1": {"id": "x1", "category": "clear_oos", "behavior": "abstain",
           "question": "Capital of France?"},
}


def _rec(qid, answer, cited=("doc_1",), pages=(10,), retrieved=("doc_1",)):
    abstained = answer == "I don't know"
    rec = {"id": qid, "answer": answer, "abstained": abstained,
           "pages": [] if abstained else list(pages),
           "cited_ids": [] if abstained else list(cited),
           "retrieved_ids": list(retrieved), "retrieved_pages": list(pages),
           "n_retrieved": len(retrieved), "candidates": None,
           "citations_verified": None if abstained else True,
           "nearest_distance": 0.3, "index": "idx"}
    return em.score_record(rec, ITEMS[qid], CHUNKS)


def _records():
    return [
        _rec("a1", "Yes, physiotherapy is covered [paramedical]."),
        _rec("a2", "Physio is covered up to $500."),
        _rec("d1", "See your Schedule of Benefits.", cited=("doc_2",), pages=(13,),
             retrieved=("doc_2",)),
        _rec("x1", "I don't know", retrieved=()),
    ]


@pytest.fixture(scope="module")
def prompt():
    return jd.load_prompt()


def _reply(f, c, reason="ok", claims=()):
    return json.dumps({"faithfulness": f, "correctness": c, "reason": reason,
                       "unsupported_claims": list(claims)})


# --- prompt ------------------------------------------------------------------------
def test_prompt_file_loads_and_renders(prompt):
    assert prompt.name == "judge_v1" and len(prompt.sha) == 12
    assert "Faithfulness" in prompt.system and "{{rubric}}" not in prompt.system
    rec = _records()[2]
    msgs = jd.render_messages(prompt, ITEMS["d1"], rec, CHUNKS)
    user = msgs[1]["content"]
    assert "{{" not in user
    assert "[doc_2] Refer to your Schedule of Benefits" in user
    assert "Schedule of Benefits, a separate document" in user  # defer note
    assert "It is in your Schedule of Benefits." in user and "Drug maximum?" in user


def test_only_answered_items_with_the_right_behaviour_are_eligible():
    recs = _records()
    assert [jd.eligible(r) for r in recs] == [True, True, True, False]
    wrong_defer = _rec("d1", "Drugs are covered.", cited=("doc_2",), pages=(13,),
                       retrieved=("doc_2",))
    assert not jd.eligible(wrong_defer)  # already failed by the judge-free check


# --- parsing ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    _reply(2, 1),
    "```json\n" + _reply(2, 1) + "\n```",
    "Here is my grade: " + _reply(2, 1) + " Thanks.",
    '{"faithfulness": "2", "correctness": "1", "reason": "ok"}',
])
def test_parse_accepts_json_in_common_wrappers(text):
    j = jd.parse_judgment(text)
    assert (j["faithfulness"], j["correctness"]) == (2, 1)
    assert isinstance(j["unsupported_claims"], list)


@pytest.mark.parametrize("text", [
    "no json here",
    '{"faithfulness": 3, "correctness": 1}',
    '{"faithfulness": 2}',
    '{"faithfulness": true, "correctness": 1}',
    '{"faithfulness": 2, "correctness": 1',
])
def test_parse_rejects_bad_replies(text):
    with pytest.raises(jd.JudgeParseError):
        jd.parse_judgment(text)


# --- running ------------------------------------------------------------------------------
def _run(records, fn, cache, prompt, **kw):
    return jd.run_judge(records, ITEMS, CHUNKS, fn, cache, prompt, "judge-m",
                        sleep_between=0, log=lambda _: None, clock=lambda: 1.0, **kw)


def test_judge_caches_and_rejudges_only_what_changed(prompt):
    calls = []
    fn = lambda msgs: (calls.append(msgs), _reply(2, 2))[1]  # noqa: E731
    cache, recs = {}, _records()
    stats = _run(recs, fn, cache, prompt)
    assert (stats["eligible"], stats["new"], stats["calls"]) == (3, 3, 3) and len(cache) == 3
    assert _run(recs, fn, cache, prompt)["calls"] == 0  # all cached

    recs[1]["answer"] = "Physio is covered."  # a new answer must be judged again
    assert _run(recs, fn, cache, prompt)["calls"] == 1
    other = jd.Prompt("judge_v2", "x" * 12, prompt.system, prompt.user, prompt.rubric)
    assert _run(recs, fn, cache, other)["calls"] == 3  # new prompt version re-judges


def test_unreadable_reply_is_retried_next_run(prompt):
    replies = iter(["garbage", _reply(2, 2), _reply(2, 2), _reply(1, 2)])
    cache, recs = {}, _records()
    stats = _run(recs, lambda m: next(replies), cache, prompt)
    assert stats["parse_errors"] == ["a1"] and stats["remaining"] == ["a1"]
    assert stats["judged"] == 2
    stats = _run(recs, lambda m: next(replies), cache, prompt)
    assert stats["calls"] == 1 and stats["judged"] == 3 and not stats["remaining"]


def test_budget_and_quota_stop_the_run(prompt):
    cache, recs = {}, _records()
    stats = _run(recs, lambda m: _reply(2, 2), cache, prompt, max_calls=1)
    assert stats["calls"] == 1 and stats["remaining"] == ["a2", "d1"]
    assert "--max-calls 1" in stats["stop_reason"]

    def out_of_quota(_):
        raise rp.GeminiQuotaExhaustedError("quota used up", retry_after_s=60.0)
    stats = _run(recs, out_of_quota, cache, prompt)
    assert stats["calls"] == 0 and stats["remaining"] == ["a2", "d1"]
    assert stats["retry_after_s"] == 60.0 and stats["judged"] == 1


# --- metrics ---------------------------------------------------------------------------------
def _judged(prompt, scores):
    """Records judged with scores {id: (faithfulness, correctness)}."""
    recs = _records()
    replies = {qid: _reply(f, c, reason=f"r-{qid}", claims=["$500"] if f < 2 else [])
               for qid, (f, c) in scores.items()}
    cache = {}
    for r in recs:
        if r["id"] in replies:
            _run([r], lambda m, q=r["id"]: replies[q], cache, prompt)
    jd.attach_judgments(recs, ITEMS, cache, prompt, "judge-m")
    return recs


def test_summary_and_strict_pass(prompt):
    recs = _judged(prompt, {"a1": (2, 2), "a2": (0, 1), "d1": (2, 2)})
    assert [r["strict_pass"] for r in recs] == [True, False, True, True]
    s = jd.summarize_judge(recs, prompt, "judge-m", ["direct_fact", "numeric", "deferred"])
    g = s["overall"]
    assert (g["n_eligible"], g["n_judged"], g["coverage"]) == (3, 3, 1.0)
    assert g["fully_correct"] == pytest.approx(2 / 3)
    assert g["hallucination_rate"] == pytest.approx(1 / 3)
    assert g["strict_pass_rate"] == 0.75
    assert [b["id"] for b in s["below_full"]] == ["a2"]
    assert s["below_full"][0]["unsupported_claims"] == ["$500"]
    assert list(s["by_category"]) == ["direct_fact", "numeric", "deferred"]


def test_strict_pass_waits_for_full_coverage(prompt):
    recs = _judged(prompt, {"a1": (2, 2)})
    assert recs[1]["strict_pass"] is None
    assert jd.summarize_judge(recs, prompt, "judge-m")["overall"]["strict_pass_rate"] is None


# --- agreement with human scores ---------------------------------------------------------------
def test_weighted_kappa_matches_known_values():
    assert jd.weighted_kappa([0, 1, 2], [0, 1, 2]) == 1.0
    assert jd.weighted_kappa([0, 1, 2], [2, 1, 0]) == pytest.approx(-1.0)
    assert jd.weighted_kappa([0, 0, 1, 2], [0, 1, 1, 2]) == pytest.approx(0.8)
    assert jd.weighted_kappa([], []) is None
    assert jd.weighted_kappa([2, 2], [2, 2]) is None  # no variation: undefined


def test_agreement_ignores_scores_for_an_older_answer(prompt):
    recs = _judged(prompt, {"a1": (2, 2), "a2": (0, 1), "d1": (2, 2)})
    rows = [
        {"id": "a1", "answer_sha": jd.answer_sha(recs[0]["answer"]), "faithfulness": 2,
         "correctness": 2},
        {"id": "a2", "answer_sha": jd.answer_sha(recs[1]["answer"]), "faithfulness": 1,
         "correctness": 1},
        {"id": "d1", "answer_sha": "old-answer!!", "faithfulness": 0, "correctness": 0},
    ]
    a = jd.agreement(recs, rows)
    assert a["stale_ids"] == ["d1"]
    f = a["dims"]["faithfulness"]
    assert f["n"] == 2 and f["exact"] == 0.5 and f["within_one"] == 1.0
    assert a["dims"]["correctness"]["exact"] == 1.0


def test_sheet_sample_is_deterministic_and_spread(prompt, tmp_path):
    recs = _records()
    s1 = jd.sample_for_sheet(recs, n=2, seed=1, category_order=["direct_fact", "numeric"])
    s2 = jd.sample_for_sheet(recs, n=2, seed=1, category_order=["direct_fact", "numeric"])
    assert [r["id"] for r in s1] == [r["id"] for r in s2] == ["a1", "a2"]  # one per category
    assert len(jd.sample_for_sheet(recs, n=50)) == 3  # only eligible items

    md = jd.render_sheet(s1, ITEMS, CHUNKS, prompt, "questions_v2.json")
    assert "## a1 (direct_fact, answer)" in md and "Faithfulness" in md
    assert "faithfulness=" not in md  # the judge's scores are not shown
    csv_path = tmp_path / "scores.csv"
    jd.write_human_csv(csv_path, s1)
    rows = jd.load_human_scores(csv_path)
    assert [r["id"] for r in rows] == ["a1", "a2"] and rows[0]["faithfulness"] is None
    csv_path.write_text("id,answer_sha,faithfulness,correctness,notes\na1,x,3,2,\n")
    with pytest.raises(ValueError, match="must be 0, 1 or 2"):
        jd.load_human_scores(csv_path)


# --- report -------------------------------------------------------------------------------------
def test_report_has_judge_section(prompt):
    from src import evaluate as ev

    recs = _judged(prompt, {"a1": (2, 2), "a2": (0, 1)})
    summary = ev.summarize(recs)
    summary["judge"] = jd.summarize_judge(recs, prompt, "judge-m")
    meta = {"date": "2026-10-28", "eval_set": "eval/x.json", "eval_set_version": "v2.0",
            "n_items": len(recs), "index": "idx", "n_chunks": 2, "gen_model": "g",
            "models_resolved": [], "embed_model": "e", "k": 4, "threshold": 0.37,
            "chunk_size": 800, "chunk_overlap": 128, "encoding": "cl100k_base",
            "git_commit": None}
    md = er.render_markdown(summary, recs, meta)
    assert "## LLM judge" in md and "**Not final:** 2 of 3" in md
    assert "| a2 | numeric | 1 | 0 |" in md
    assert "No human scores yet" in md
    assert "Judged 2/3" not in ev.format_summary(summary, "idx")
    assert "judged 2/3" in ev.format_summary(summary, "idx")
    assert er.metrics_json(summary, meta)["judge"]["overall"]["n_judged"] == 2


def test_cached_records_never_call_the_api():
    from src import evaluate as ev

    qset = {"idk_answer": "I don't know",
            "in_scope": [{"id": "in_01", "question": "Is physio covered?"}],
            "out_of_scope": [{"id": "out_01", "question": "Capital of France?"}]}
    cache = {}
    ev.run_eval({**qset, "out_of_scope": []},
                lambda q: ("Physio is covered.", [7], [{"id": "doc_1", "score": 0.3}]),
                "idx", cache=cache, sleep_between=0, log=lambda _: None)
    records, total = ev.cached_records(qset, "idx", cache)
    assert [r["id"] for r in records] == ["in_01"] and total == 2
