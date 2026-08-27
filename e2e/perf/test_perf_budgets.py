"""Page-performance budgets — runs against the prod overlay (`make e2e-perf`).

3 fresh-context runs per route; fail only if 2 of 3 miss any budget metric.
Per-route metrics land in ``e2e/perf/artifacts/<route>/metrics.json`` (the
advisory artifact). Infrastructure errors fail the lane — a lane that skips on
error can never catch a regression.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from e2e.helpers import perf_metrics

BUDGETS = json.loads(Path("e2e/perf/budgets.json").read_text())
ARTIFACTS = Path("e2e/perf/artifacts")

RUNS = 3


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
def test_page_budget(route: str, browser, frontend_base_url: str, analytics) -> None:
    budget = BUDGETS[route]
    url = _resolve_url(route, frontend_base_url)
    out = ARTIFACTS / (route.lstrip("/").replace("/", "_").replace(":", "") or "root")

    results = [perf_metrics.collect_once(browser, url) for _ in range(RUNS)]
    perf_metrics.write_artifacts(out, results)

    misses = perf_metrics.count_over_budget(results, budget)
    assert misses < 2, (
        f"{route}: {misses}/{RUNS} runs over budget {budget} — "
        f"LCP={[round(r.lcp) for r in results]}ms "
        f"CLS={[round(r.cls, 4) for r in results]} "
        f"TBT={[round(r.tbt) for r in results]}ms"
    )
