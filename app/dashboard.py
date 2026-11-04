"""
dashboard.py — turn GET /stats output into the tables the Monitoring page
charts (PLAN.md M5). Framework-free apart from pandas, so it is unit-tested.

Streamlit draws charts with Vega-Lite, which reads some characters in a column
name as a field path: dots, square brackets, backslashes and straight quotes.
A column named '"I don't know" rate' or 'threshold (0.37)' breaks the chart
("Access path missing closing bracket"). So every chart column here uses
plain words; numbers like the threshold value go in captions instead.
"""

from __future__ import annotations

import pandas as pd

# Characters Vega-Lite treats as field-path syntax.
UNSAFE_CHARS = set(".[]\\\"'")

QUESTIONS = "questions"
IDK_RATE = "share answered with I do not know"
LATENCY_P50 = "median"
LATENCY_P95 = "95th percentile"
DISTANCE = "median closest distance"
THRESHOLD = "relevance threshold"


def daily_frame(stats: dict) -> pd.DataFrame:
    """The per-day series, indexed by day (also the page's table view)."""
    return pd.DataFrame(stats["by_day"]).set_index("day")


def chart_frames(stats: dict) -> dict[str, pd.DataFrame]:
    """One DataFrame per chart, with Vega-safe column names."""
    df = daily_frame(stats)
    frames = {
        "questions": df[["requests"]].rename(columns={"requests": QUESTIONS}),
        "idk_rate": df[["idk_rate"]].rename(columns={"idk_rate": IDK_RATE}),
        "latency": df[["latency_p50_s", "latency_p95_s"]].rename(
            columns={"latency_p50_s": LATENCY_P50, "latency_p95_s": LATENCY_P95}),
        "distance": df[["nearest_distance_median"]].rename(
            columns={"nearest_distance_median": DISTANCE}),
    }
    if stats.get("threshold") is not None:
        frames["distance"][THRESHOLD] = stats["threshold"]
    return frames


def unsafe_columns(frames: dict[str, pd.DataFrame]) -> list[str]:
    """Column names Vega-Lite would misread (should always be empty)."""
    return [str(c) for f in frames.values() for c in f.columns
            if set(str(c)) & UNSAFE_CHARS]
