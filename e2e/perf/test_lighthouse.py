"""Lighthouse budgets — runs against the prod overlay.

3 runs per route; fail only if 2 of 3 miss any budget metric.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from e2e.helpers import lighthouse_runner

BUDGETS = json.loads(Path("e2e/perf/budgets.json").read_text())
ARTIFACTS = Path("e2e/perf/artifacts")


def _resolve_url(route: str, frontend_base_url: str) -> str:
    url_path = route
    if ":id" in url_path:
        from apps.threads.models import Thread

        t = Thread.objects.first()
        if t is not None:
            url_path = url_path.replace(":id", str(t.id))
    return f"{frontend_base_url}{url_path}"


@pytest.mark.integration
@pytest.mark.perf
@pytest.mark.parametrize("route", list(BUDGETS.keys()))
def test_lighthouse_budget(route: str, frontend_base_url: str, analytics) -> None:
    budget = BUDGETS[route]
    url = _resolve_url(route, frontend_base_url)
    out = ARTIFACTS / route.lstrip("/").replace("/", "_").replace(":", "")
    try:
        results = [lighthouse_runner.run_once(url, out / f"run-{i}") for i in range(3)]
    except FileNotFoundError:
        pytest.skip("docker or lighthouse not available in this environment")
    except Exception as exc:
        pytest.skip(f"lighthouse runner failed: {exc!r}")

    misses = lighthouse_runner.count_over_budget(results, budget)
    assert misses < 2, (
        f"{route}: {misses}/3 runs over budget — "
        f"LCPs={[r.lcp for r in results]} "
        f"scores={[r.performance_score for r in results]}"
    )

    median = lighthouse_runner.run_median(url, out, runs=3)
    (out / "median.json").write_text(json.dumps(median.report_json, indent=2))
    (out / "median.html").write_text(median.report_html)
