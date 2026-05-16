"""GHA workflow sanity checks."""

from __future__ import annotations

from pathlib import Path

import yaml


def _wf_path() -> Path:
    for p in (Path("/app/.github/workflows/e2e.yml"), Path(".github/workflows/e2e.yml")):
        if p.exists():
            return p
    raise FileNotFoundError(".github/workflows/e2e.yml not found")


def test_e2e_workflow_has_six_lane_jobs() -> None:
    wf = yaml.safe_load(_wf_path().read_text())
    jobs = wf["jobs"]
    for lane in ("e2e-ui", "e2e-api", "e2e-ws", "e2e-visual", "e2e-a11y", "e2e-perf"):
        assert lane in jobs, f"missing GHA job: {lane}"


def test_e2e_workflow_has_summary_job() -> None:
    wf = yaml.safe_load(_wf_path().read_text())
    assert "e2e-summary" in wf["jobs"]
    summary = wf["jobs"]["e2e-summary"]
    assert "if" in summary and "always()" in summary["if"]
