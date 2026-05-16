"""Unit-shape test for the lighthouse_runner helper (no actual run)."""

from __future__ import annotations


def test_lighthouse_helper_api() -> None:
    from e2e.helpers import lighthouse_runner

    for attr in ("run_once", "run_median", "Result", "count_over_budget"):
        assert hasattr(lighthouse_runner, attr), f"missing {attr}"


def test_count_over_budget_logic() -> None:
    from e2e.helpers.lighthouse_runner import Result, count_over_budget

    good = Result(
        lcp=1000, cls=0.05, tbt=100, performance_score=0.95, report_html="", report_json={}
    )
    bad = Result(
        lcp=5000, cls=0.30, tbt=900, performance_score=0.40, report_html="", report_json={}
    )
    budget = {"LCP": 2500, "CLS": 0.1, "TBT": 300, "performance": 0.85}
    assert count_over_budget([good, good, good], budget) == 0
    assert count_over_budget([good, bad, bad], budget) == 2
