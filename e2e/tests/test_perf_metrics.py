"""Unit tests for the perf_metrics helper's pure functions (no browser)."""

from __future__ import annotations

import json

import pytest


def test_perf_helper_api() -> None:
    from e2e.helpers import perf_metrics

    for attr in (
        "collect_once",
        "median_result",
        "Result",
        "count_over_budget",
        "tbt_from_long_tasks",
        "write_artifacts",
    ):
        assert hasattr(perf_metrics, attr), f"missing {attr}"


def test_tbt_counts_only_the_over_50ms_tail() -> None:
    from e2e.helpers.perf_metrics import tbt_from_long_tasks

    assert tbt_from_long_tasks([]) == 0.0
    assert tbt_from_long_tasks([49.9, 50.0]) == 0.0
    assert tbt_from_long_tasks([120.0, 80.0]) == pytest.approx(100.0)


def test_count_over_budget_logic() -> None:
    from e2e.helpers.perf_metrics import Result, count_over_budget

    good = Result(lcp=1000, cls=0.05, tbt=100)
    bad = Result(lcp=5000, cls=0.30, tbt=900)
    budget = {"LCP": 2500, "CLS": 0.1, "TBT": 300}
    assert count_over_budget([good, good, good], budget) == 0
    assert count_over_budget([good, bad, bad], budget) == 2
    # One metric over is enough, and a run is only ever counted once.
    assert count_over_budget([Result(lcp=1000, cls=0.5, tbt=900)], budget) == 1
    # Absent budget keys don't bind.
    assert count_over_budget([bad], {}) == 0


def test_median_result_is_per_metric() -> None:
    from e2e.helpers.perf_metrics import Result, median_result

    rs = [
        Result(lcp=1, cls=0.3, tbt=30),
        Result(lcp=2, cls=0.1, tbt=10),
        Result(lcp=3, cls=0.2, tbt=20),
    ]
    m = median_result(rs)
    assert (m.lcp, m.cls, m.tbt) == (2, 0.2, 20)


def test_write_artifacts_shape(tmp_path) -> None:
    from e2e.helpers.perf_metrics import Result, write_artifacts

    write_artifacts(tmp_path / "r", [Result(lcp=1.0, cls=0.0, tbt=0.0)])
    data = json.loads((tmp_path / "r" / "metrics.json").read_text())
    assert data["runs"][0]["lcp"] == 1.0
    assert data["median"]["lcp"] == 1.0
