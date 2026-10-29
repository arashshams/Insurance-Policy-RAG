"""
Offline tests for the M2 CI pieces: the pipeline fingerprint in the answer
cache, eval subsets, the smoke-eval gates and the weekly model check.
No API key and no network needed.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

pytest.importorskip("openai")

from src import eval_set as es  # noqa: E402
from src import evaluate as ev  # noqa: E402
from src import model_check as mc  # noqa: E402
from src import rag_pipeline as rp  # noqa: E402

QSET = {
    "idk_answer": "I don't know",
    "in_scope": [{"id": "in_01", "question": "Is physio covered?", "expected_keywords": ["physio"]},
                 {"id": "in_02", "question": "Is dental covered?"}],
    "out_of_scope": [{"id": "out_01", "question": "Capital of France?"}],
}
KW = dict(sleep_between=0, log=lambda _: None)


def _answer(q):
    if "France" in q:
        return "I don't know", [], []
    return f"Yes: {q}", [7], [{"id": "doc_1", "score": 0.3}]


# --- pipeline fingerprint ------------------------------------------------------------
def test_prompt_change_reasks_cached_answers(monkeypatch):
    calls = []
    fn = lambda q: (calls.append(q), _answer(q))[1]  # noqa: E731
    cache = {}
    ev.run_eval(QSET, fn, "idx", cache=cache, **KW)
    assert len(calls) == 3
    assert {r["pipeline"] for r in cache.values()} == {rp.pipeline_fingerprint()}

    ev.run_eval(QSET, fn, "idx", cache=cache, **KW)
    assert len(calls) == 3  # same pipeline: all cached

    monkeypatch.setattr(rp, "RAG_SYSTEM_MESSAGE", rp.RAG_SYSTEM_MESSAGE + "\nBe brief.")
    ev.run_eval(QSET, fn, "idx", cache=cache, **KW)
    assert len(calls) == 6  # new prompt: every answer asked again


def test_fingerprint_covers_generation_and_chunking_settings(monkeypatch):
    base = rp.pipeline_fingerprint()
    for name, value in (("GEN_MAX_TOKENS", 2048), ("CHUNK_SIZE", 400),
                        ("RAG_USER_TEMPLATE", "{context}{question}")):
        with monkeypatch.context() as m:
            m.setattr(rp, name, value)
            assert rp.pipeline_fingerprint() != base, name
    assert rp.pipeline_fingerprint() == base


def test_answers_cached_before_fingerprinting_are_adopted_not_reasked():
    calls, saves = [], []
    fn = lambda q: (calls.append(q), _answer(q))[1]  # noqa: E731
    cache = {}
    ev.run_eval(QSET, fn, "idx", cache=cache, **KW)
    for rec in cache.values():
        del rec["pipeline"]  # what answers cached by older code look like
    calls.clear()
    ev.run_eval(QSET, fn, "idx", cache=cache, save_cache=saves.append, **KW)
    assert calls == [] and saves  # reused, and the cache was saved with the fingerprint
    assert {r["pipeline"] for r in cache.values()} == {rp.pipeline_fingerprint()}


# --- subsets ------------------------------------------------------------------------------
def test_smoke_subset_is_valid_and_covers_every_category():
    v2 = es.load_eval_set(es.DEFAULT_SET)
    ids = es.load_subset(REPO_ROOT / "eval" / "smoke_v2.txt")
    sub = es.filter_set(v2, ids)
    items = es.items_of(sub)
    assert len(items) == len(ids) == 12
    assert {i["category"] for i in items} == set(v2["categories"])
    assert {i["behavior"] for i in items} == {"answer", "defer", "abstain"}
    assert es.validate_eval_set(sub) == []


def test_subset_file_parsing_and_errors(tmp_path):
    f = tmp_path / "s.txt"
    f.write_text("# comment\n\nin_02   # trailing comment\nout_01\n", encoding="utf-8")
    ids = es.load_subset(f)
    assert ids == ["in_02", "out_01"]
    sub = es.filter_set(QSET, ids)
    assert [i["id"] for i in es.items_of(sub)] == ["in_02", "out_01"]
    with pytest.raises(ValueError, match="unknown ids \\['nope'\\]"):
        es.filter_set(QSET, ["in_01", "nope"])
    with pytest.raises(ValueError, match="duplicate ids \\['in_01'\\]"):
        es.filter_set(QSET, ["in_01", "in_01"])


# --- gates ------------------------------------------------------------------------------------
def _summary(answer_fn):
    _, s = ev.run_eval(QSET, answer_fn, "idx", **KW)
    return s


def test_gates_pass_on_a_clean_run():
    gates = ev.check_gates(_summary(_answer))
    assert all(g["ok"] for g in gates)
    assert "| pass |" in ev.format_gates(gates)


def test_guardrail_gate_fails_when_out_of_scope_is_answered():
    def leaky(q):
        return ("Paris.", [1], [{"id": "doc_9", "score": 0.3}]) if "France" in q else _answer(q)
    gates = {g["gate"]: g for g in ev.check_gates(_summary(leaky))}
    guard = next(g for name, g in gates.items() if name.startswith("Guardrail"))
    assert not guard["ok"] and "out_01" in guard["detail"]
    assert "**FAIL**" in ev.format_gates(list(gates.values()))


def test_wrongful_abstention_and_failure_count_gates():
    def shy(q):
        return ("I don't know", [], []) if "dental" in q else _answer(q)
    gates = ev.check_gates(_summary(shy), max_failures=1)
    assert [g["ok"] for g in gates] == [True, False, True]  # one failure is tolerated
    assert [g["ok"] for g in ev.check_gates(_summary(shy), max_failures=0)] == [True, False, False]


def test_step_summary_is_written_only_on_github(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    ev._write_step_summary("ignored")  # no-op outside Actions
    out = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(out))
    ev._write_step_summary("| Gate |")
    assert out.read_text(encoding="utf-8") == "| Gate |\n"


# --- weekly model check -------------------------------------------------------------------------
def test_flash_version_only_matches_plain_flash_models():
    assert mc.flash_version("gemini-3.8-flash") == (3, 8)
    assert mc.flash_version("models/gemini-4-flash") == (4,)
    for name in ("gemini-3.8-flash-lite", "gemini-3.9-flash-preview-11-2026",
                 "gemini-3.8-flash-001", "gemini-flash-latest", "gemini-3.8-pro"):
        assert mc.flash_version(name) is None, name


def test_check_reports_missing_and_newer_models():
    pinned = {"generator": "gemini-3.8-flash", "judge": "gemini-3.6-flash"}
    ok = mc.check(["gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.8-flash-lite"], pinned)
    assert not ok["action_needed"] and not ok["upgrade_available"]
    assert "Nothing to do" in mc.render(ok, pinned)

    r = mc.check(["gemini-3.8-flash", "gemini-3.10-flash", "gemini-4-flash",
                  "gemini-4.1-flash-lite"], pinned)
    assert r["missing"] == {"judge": "gemini-3.6-flash"} and r["action_needed"]
    assert r["newer"] == ["gemini-4-flash", "gemini-3.10-flash"]  # numeric, newest first
    text = mc.render(r, pinned)
    assert "**Action needed:**" in text and "`gemini-4-flash`" in text


def test_model_check_main_writes_github_outputs(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    out = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setattr(mc, "list_models", lambda key: ["gemini-9-flash"])
    monkeypatch.setattr(rp, "GEN_MODEL", "gemini-3.8-flash")
    report = tmp_path / "report.md"
    assert mc.main(["--out", str(report)]) == 0
    assert out.read_text() == "action_needed=true\nupgrade_available=true\n"
    assert "gemini-9-flash" in report.read_text()


def test_model_check_without_key_or_network(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(rp, "_read_api_key", lambda: (_ for _ in ()).throw(RuntimeError("no key")))
    assert mc.main([]) == 2

    monkeypatch.setattr(rp, "_read_api_key", lambda: "test")

    def offline(key):
        raise OSError("network down")
    monkeypatch.setattr(mc, "list_models", offline)
    assert mc.main([]) == 2


def test_workflows_are_valid_yaml():
    yaml = pytest.importorskip("yaml")
    for name in ("tests.yml", "smoke-eval.yml", "full-eval.yml", "model-check.yml"):
        wf = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / name).read_text())
        assert "jobs" in wf, name
