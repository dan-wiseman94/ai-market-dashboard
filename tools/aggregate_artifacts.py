#!/usr/bin/env python3
"""Consume per-lane CI artifacts and emit a single PR-comment-ready markdown blob.

The e2e workflow's per-lane jobs write ``artifacts/<lane>-result.json`` (with
``passed``, ``tests``, ``artifacts``); this script reads them all and produces a
matrix table plus an a11y breakdown.
"""

from __future__ import annotations

import json
from pathlib import Path

LANES = ("ui", "api", "ws", "visual", "a11y", "perf")


def build_summary() -> str:
    lines = [
        "## E2E results",
        "",
        "| Lane | Result | Tests | Artifacts |",
        "|------|--------|------:|-----------|",
    ]
    for lane in LANES:
        result_file = Path(f"artifacts/{lane}-result.json")
        if not result_file.exists():
            lines.append(f"| {lane} | missing | - | - |")
            continue
        data = json.loads(result_file.read_text())
        icon = "PASS" if data.get("passed") else "FAIL"
        artifacts = data.get("artifacts", {})
        artifact_links = " / ".join(f"[{n}]({u})" for n, u in artifacts.items()) or "-"
        lines.append(f"| {lane} | {icon} | {data.get('tests', '-')} | {artifact_links} |")

    a11y_dir = Path("artifacts/a11y-violations")
    if a11y_dir.exists():
        lines += ["", "### A11y violations"]
        for f in sorted(a11y_dir.glob("*.json")):
            v = json.loads(f.read_text())
            lines.append(f"- `{f.stem}`: {len(v)} violations")

    return "\n".join(lines)


if __name__ == "__main__":
    print(build_summary())
