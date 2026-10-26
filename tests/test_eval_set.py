"""
Offline checks on the versioned evaluation set (eval/questions_v2.json).

The eval set is the ground truth behind every quality claim, so it is tested
like code: schema, evidence phrases actually present on their stated pages of
the shipped demo index, the review table kept in sync, and every v1 question
carried over. No API key needed.
"""

import shutil
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src import eval_set as es  # noqa: E402

V1_PATH = REPO_ROOT / "notebooks" / "eval" / "eval_questions.json"


@pytest.fixture(scope="module")
def v2():
    return es.load_eval_set(es.DEFAULT_SET)


def test_v2_schema_is_valid(v2):
    assert es.validate_eval_set(v2) == []


def test_v2_evidence_is_on_stated_pages_of_demo_index(v2, tmp_path_factory):
    pytest.importorskip("chromadb")
    from src import rag_pipeline as rp

    # Open a COPY: Chroma rewrites index files on open.
    idx = tmp_path_factory.mktemp("idx") / "demo_index"
    shutil.copytree(REPO_ROOT / "app" / "demo_index", idx)
    pages = es.page_texts_from_collection(rp.load_persistent_collection(persist_dir=str(idx)))
    assert es.check_evidence(v2, pages) == []


def test_v2_review_table_is_up_to_date(v2):
    expected = es.render_review_markdown(v2, es.DEFAULT_SET.name)
    actual = es.review_path_for(es.DEFAULT_SET).read_text(encoding="utf-8")
    assert actual == expected, "eval review table is stale: run `python -m src.eval_set`"


def test_v2_carries_over_every_v1_question(v2):
    import json

    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    v1_questions = {q["id"]: q["question"] for q in v1["in_scope"] + v1["out_of_scope"]}
    carried = {i["v1_id"]: i["question"] for i in v2["items"] if i.get("v1_id")}
    assert carried == v1_questions  # same ids, unchanged wording


def test_v2_has_enough_of_each_behavior(v2):
    from collections import Counter

    counts = Counter(i["behavior"] for i in v2["items"])
    # Abstention precision/recall needs a meaningful number of both classes.
    assert counts["abstain"] >= 15 and counts["answer"] >= 30 and counts["defer"] >= 3


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["items"].append(dict(d["items"][0])), "duplicate id"),
    (lambda d: d["items"][0].update(category="nope"), "unknown category"),
    (lambda d: d["items"][0].update(reference_answer=""), "needs a reference_answer"),
    (lambda d: d["items"][0]["evidence"][0].update(page=999), "not in expected_pages"),
    (lambda d: next(i for i in d["items"] if i["behavior"] == "abstain").update(
        expected_pages=[3]), "must not have 'expected_pages'"),
])
def test_validator_catches_mistakes(v2, mutate, message):
    import copy

    data = copy.deepcopy(v2)
    mutate(data)
    assert any(message in p for p in es.validate_eval_set(data))


def test_evidence_check_catches_wrong_page(v2):
    import copy

    data = copy.deepcopy(v2)
    item = data["items"][0]
    item["evidence"] = [{"page": 10, "text": "a phrase that is not in the policy"}]
    problems = es.check_evidence({"items": [item]}, {10: es.normalize_text("other text")})
    assert problems and "not found on page 10" in problems[0]


def test_normalize_text_ignores_pdf_spacing_and_quotes():
    assert es.normalize_text("31 -day grace") == es.normalize_text("31-day grace")
    assert es.normalize_text("We’ll pay") == es.normalize_text("We'll pay")
