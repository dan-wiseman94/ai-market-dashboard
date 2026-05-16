"""GHA workflow sanity checks."""

from __future__ import annotations

from pathlib import Path

import yaml


def _wf_path() -> Path:
    for p in (Path("/app/.github/workflows/e2e.yml"), Path(".github/workflows/e2e.yml")):
        if p.exists():
            return p
    raise FileNotFoundError(".github/workflows/e2e.yml not found")


def test_e2e_workflow_has_ui_job() -> None:
    """e2e.yml currently has a single 'ui' job; will fan out when other
    lanes gain real tests."""
    wf = yaml.safe_load(_wf_path().read_text())
    assert "ui" in wf["jobs"]


def test_e2e_workflow_runs_pytest_against_ui_lane() -> None:
    wf = yaml.safe_load(_wf_path().read_text())
    steps = wf["jobs"]["ui"]["steps"]
    runs = [s.get("run") or "" for s in steps]
    assert any("pytest e2e/ui/" in r for r in runs), (
        "expected a step that runs pytest against e2e/ui/"
    )
