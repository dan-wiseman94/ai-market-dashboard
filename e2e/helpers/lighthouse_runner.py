"""Lighthouse runner — shells out to the ``lighthouse`` npm CLI inside the
frontend container (which already has node).

The web container that owns the API doesn't have lighthouse; the runner
``docker compose exec``-s into ``frontend`` for the actual run.
"""

from __future__ import annotations

import json
import statistics
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Result:
    lcp: float
    cls: float
    tbt: float
    performance_score: float
    report_html: str
    report_json: dict


def run_once(url: str, out_dir: Path) -> Result:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_base = out_dir / "run"
    cmd = [
        "docker",
        "compose",
        "exec",
        "-T",
        "frontend",
        "npx",
        "lighthouse",
        url,
        "--output=json",
        "--output=html",
        f"--output-path={out_base}",
        "--chrome-flags=--headless=new --no-sandbox --disable-gpu",
        "--only-categories=performance",
        "--throttling-method=provided",
    ]
    subprocess.run(cmd, check=True, timeout=180)
    json_path = Path(f"{out_base}.report.json")
    html_path = Path(f"{out_base}.report.html")
    report = json.loads(json_path.read_text())
    audits = report["audits"]
    return Result(
        lcp=audits["largest-contentful-paint"]["numericValue"],
        cls=audits["cumulative-layout-shift"]["numericValue"],
        tbt=audits["total-blocking-time"]["numericValue"],
        performance_score=report["categories"]["performance"]["score"],
        report_html=html_path.read_text(),
        report_json=report,
    )


def run_median(url: str, out_dir: Path, runs: int = 3) -> Result:
    results = [run_once(url, out_dir / f"run-{i}") for i in range(runs)]
    medians = {
        "lcp": statistics.median(r.lcp for r in results),
        "cls": statistics.median(r.cls for r in results),
        "tbt": statistics.median(r.tbt for r in results),
        "performance_score": statistics.median(r.performance_score for r in results),
    }
    canonical = min(results, key=lambda r: abs(r.performance_score - medians["performance_score"]))
    return Result(
        lcp=medians["lcp"],
        cls=medians["cls"],
        tbt=medians["tbt"],
        performance_score=medians["performance_score"],
        report_html=canonical.report_html,
        report_json=canonical.report_json,
    )


def count_over_budget(results: list[Result], budget: dict) -> int:
    count = 0
    for r in results:
        if r.lcp > budget.get("LCP", float("inf")):
            count += 1
            continue
        if r.cls > budget.get("CLS", float("inf")):
            count += 1
            continue
        if r.tbt > budget.get("TBT", float("inf")):
            count += 1
            continue
        if r.performance_score < budget.get("performance", 0):
            count += 1
            continue
    return count
