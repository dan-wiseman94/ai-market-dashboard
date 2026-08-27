"""Playwright-based page-performance metrics — LCP / CLS / TBT budgets.

PerformanceObservers are injected before navigation (``add_init_script``), so
the perf lane runs entirely inside the ``worker`` container it is invoked in
(playwright + chromium) — no docker-in-docker, no external CLI.

TBT here is the long-task approximation: sum of (task duration − 50 ms) over
every long task observed up to the sample point. Comparable run-to-run against
the same build; not identical to Lighthouse's TTI-windowed TBT.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

from playwright.sync_api import Browser

_OBSERVER_JS = """
(() => {
  const perf = { lcp: 0, cls: 0, longTasks: [] };
  window.__e2ePerf = perf;
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) perf.lcp = e.startTime;
  }).observe({ type: "largest-contentful-paint", buffered: true });
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) if (!e.hadRecentInput) perf.cls += e.value;
  }).observe({ type: "layout-shift", buffered: true });
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) perf.longTasks.push(e.duration);
  }).observe({ type: "longtask", buffered: true });
})();
"""


@dataclass
class Result:
    lcp: float  # ms
    cls: float  # unitless score
    tbt: float  # ms


def tbt_from_long_tasks(durations: list[float]) -> float:
    return float(sum(max(0.0, d - 50.0) for d in durations))


def collect_once(browser: Browser, url: str, *, settle_ms: int = 3_000) -> Result:
    """One cold sample: fresh context, observers registered before navigation.

    The settle window lets the SPA hydrate past the ``load`` event so late LCP
    candidates and long tasks are captured. Navigation failures raise — an
    unreachable frontend must fail the lane, not skip it.
    """
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    try:
        context.add_init_script(_OBSERVER_JS)
        page = context.new_page()
        page.goto(url, wait_until="load")
        page.wait_for_timeout(settle_ms)
        raw = page.evaluate("window.__e2ePerf")
        return Result(
            lcp=float(raw["lcp"]),
            cls=float(raw["cls"]),
            tbt=tbt_from_long_tasks([float(d) for d in raw["longTasks"]]),
        )
    finally:
        context.close()


def median_result(results: list[Result]) -> Result:
    return Result(
        lcp=statistics.median(r.lcp for r in results),
        cls=statistics.median(r.cls for r in results),
        tbt=statistics.median(r.tbt for r in results),
    )


def count_over_budget(results: list[Result], budget: dict) -> int:
    """Number of runs missing any budget metric. Absent budget keys don't bind."""
    count = 0
    for r in results:
        if (
            r.lcp > budget.get("LCP", float("inf"))
            or r.cls > budget.get("CLS", float("inf"))
            or r.tbt > budget.get("TBT", float("inf"))
        ):
            count += 1
    return count


def write_artifacts(out_dir: Path, results: list[Result]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "runs": [asdict(r) for r in results],
        "median": asdict(median_result(results)),
    }
    (out_dir / "metrics.json").write_text(json.dumps(payload, indent=2))
