"""
Regression test: the app's example-question buttons must be verbatim
entries from the calibration eval set (notebooks/eval/eval_questions.json).

Why this exists: on 2026-09-03 a friendlier paraphrase ("Are pre-authorizations
required?") silently abstained on the live app because "pre-authorization"
never appears in the source policy -- only "Prior Authorization" does. The
paraphrase read fine to a human but its retrieval score was never re-verified
against the eval harness. This test catches that class of bug WITHOUT calling
any embedding/LLM API: it only checks that every string in
app/streamlit_app.py's EXAMPLE_QUESTIONS list is copied verbatim from an
in-scope question in eval_questions.json, whose retrieval hit rate IS
calibrated by 04_evaluation.ipynb.

This is a necessary check, not a sufficient one: it does not re-verify
retrieval against the live index (that's still 04_evaluation.ipynb's job,
which needs a GEMINI_API_KEY). It only prevents someone from swapping in an
untested paraphrase again.

Run directly:  python tests/test_example_questions.py
Run via pytest: pytest tests/test_example_questions.py   (if pytest is installed)
"""

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_FILE = REPO_ROOT / "app" / "streamlit_app.py"
EVAL_FILE = REPO_ROOT / "notebooks" / "eval" / "eval_questions.json"


def _load_example_questions():
    """Extract EXAMPLE_QUESTIONS from app/streamlit_app.py via AST, so we
    never have to import (and execute) the Streamlit module just to read a
    list literal."""
    tree = ast.parse(APP_FILE.read_text(encoding="utf-8"), filename=str(APP_FILE))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "EXAMPLE_QUESTIONS"
            for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"EXAMPLE_QUESTIONS assignment not found in {APP_FILE}")


def _load_eval_in_scope_questions():
    data = json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    return [q["question"] for q in data["in_scope"]]


def test_example_questions_are_verbatim_eval_questions():
    examples = _load_example_questions()
    eval_questions = _load_eval_in_scope_questions()

    assert examples, "EXAMPLE_QUESTIONS is empty"

    missing = [q for q in examples if q not in eval_questions]
    assert not missing, (
        "The following example question(s) in app/streamlit_app.py are not "
        "verbatim entries in notebooks/eval/eval_questions.json's in_scope "
        "set, so their retrieval score has never been calibrated:\n"
        + "\n".join(f"  - {q!r}" for q in missing)
        + "\n\nEither use the exact eval wording, or add the new wording as "
        "an in_scope question in eval_questions.json and re-run "
        "04_evaluation.ipynb before shipping it as an example."
    )


if __name__ == "__main__":
    test_example_questions_are_verbatim_eval_questions()
    print("OK: all example questions are verbatim eval_questions.json entries.")
