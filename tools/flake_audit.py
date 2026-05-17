#!/usr/bin/env python3
"""Re-runs every e2e lane 3x and logs per-test pass/fail ratios.

Reads JUnit XML outputs from each run, computes flake rates, and writes
``flake_audit.json`` to the repo root. Used by the nightly GHA cron.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

RUNS = 3
LANES = ["ui", "api", "ws"]
ARTIFACTS = Path("flake_audit_runs")


def run_lane(lane: str, run_idx: int) -> Path:
    out = ARTIFACTS / f"{lane}-run-{run_idx}.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    container = "worker" if lane in ("ui", "visual", "a11y") else "web"
    subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "--workdir",
            "/app",
            container,
            "pytest",
            f"e2e/{lane}/",
            "-n",
            "4",
            "-m",
            "integration",
            f"--junit-xml={out}",
        ],
        check=False,
    )
    return out


_TESTCASE_OPEN_RE = re.compile(
    r"<testcase\b[^>]*\bclassname=\"([^\"]+)\"[^>]*\bname=\"([^\"]+)\"[^>]*?(/?)>",
)
_FAILED_INNER_RE = re.compile(r"<(failure|error)\b")


def parse_junit(path: Path) -> dict[str, bool]:
    """Tiny line-level JUnit XML parser.

    We only need ``classname::name`` and whether the case contained
    ``<failure>`` or ``<error>``. Hand-rolled to avoid the stdlib XML parser
    (which semgrep flags for XXE risk even on trusted input).
    """
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    results: dict[str, bool] = {}
    pos = 0
    while True:
        m = _TESTCASE_OPEN_RE.search(text, pos)
        if not m:
            break
        classname, name, _self_close = m.group(1, 2, 3)
        key = f"{classname}::{name}"
        # Self-closing testcase = passed (no nested failure/error)
        if _self_close == "/":
            results[key] = True
            pos = m.end()
            continue
        # Otherwise scan up to the matching </testcase>
        close = text.find("</testcase>", m.end())
        body = text[m.end() : close] if close != -1 else text[m.end() :]
        results[key] = not _FAILED_INNER_RE.search(body)
        pos = close + len("</testcase>") if close != -1 else len(text)
    return results


def main() -> int:
    stats: dict[str, list[bool]] = defaultdict(list)
    for lane in LANES:
        for i in range(RUNS):
            out = run_lane(lane, i)
            for name, passed in parse_junit(out).items():
                stats[name].append(passed)

    flaky = []
    for name, runs in stats.items():
        if 0 < sum(runs) < len(runs):
            flaky.append(
                {
                    "test": name,
                    "passes": sum(runs),
                    "runs": len(runs),
                    "flake_rate": round(1 - sum(runs) / len(runs), 3),
                }
            )

    flaky.sort(key=lambda x: x["flake_rate"], reverse=True)
    Path("flake_audit.json").write_text(
        json.dumps(
            {"total_tests": len(stats), "flaky_count": len(flaky), "flaky": flaky[:20]},
            indent=2,
        )
    )
    print(f"Total tests: {len(stats)} | Flaky: {len(flaky)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
