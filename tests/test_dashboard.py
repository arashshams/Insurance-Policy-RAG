"""
Offline tests for the Monitoring page's chart data (app/dashboard.py).

Streamlit charts with Vega-Lite, which reads dots, brackets, backslashes and
straight quotes in a column name as a field path; a column like
'"I don't know" rate' broke the live page ("Access path missing closing
bracket"). These tests keep every chart column plain.
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
pd = pytest.importorskip("pandas")


@pytest.fixture(scope="module")
def dashboard():
    spec = importlib.util.spec_from_file_location("dashboard", REPO_ROOT / "app" / "dashboard.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stats(threshold=0.37):
    day = {"requests": 2, "idk_rate": 0.5, "latency_p50_s": 3.1, "latency_p95_s": 5.4,
           "nearest_distance_median": 0.33}
    return {"threshold": threshold,
            "by_day": [{"day": "2026-11-03", **day}, {"day": "2026-11-04", **day}]}


def test_every_chart_column_is_safe_for_vega_lite(dashboard):
    frames = dashboard.chart_frames(_stats())
    assert set(frames) == {"questions", "idk_rate", "latency", "distance"}
    assert dashboard.unsafe_columns(frames) == []


def test_unsafe_names_are_caught(dashboard):
    bad = {"x": pd.DataFrame({"\"I don't know\" rate": [1], "threshold (0.37)": [2]})}
    assert dashboard.unsafe_columns(bad) == ["\"I don't know\" rate", "threshold (0.37)"]


def test_threshold_line_only_when_known(dashboard):
    with_line = dashboard.chart_frames(_stats())["distance"]
    assert list(with_line.columns) == [dashboard.DISTANCE, dashboard.THRESHOLD]
    assert (with_line[dashboard.THRESHOLD] == 0.37).all()
    without = dashboard.chart_frames(_stats(threshold=None))["distance"]
    assert list(without.columns) == [dashboard.DISTANCE]


def test_days_are_the_index(dashboard):
    frames = dashboard.chart_frames(_stats())
    assert list(frames["questions"].index) == ["2026-11-03", "2026-11-04"]
    assert frames["questions"][dashboard.QUESTIONS].tolist() == [2, 2]
