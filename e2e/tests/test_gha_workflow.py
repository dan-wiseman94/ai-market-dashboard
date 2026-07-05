"""GHA workflow contract checks — assert e2e.yml keeps running the lanes it must.

Asserts the full contract across ALL jobs, not any single named job (so it also
survives a future fan-out into a per-lane matrix): the api lane, schemathesis,
the render-chart integration test, and teardown. A job rename or refactor that
dropped one of these would otherwise stay silently green.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def _wf() -> dict:
    for p in (Path("/app/.github/workflows/e2e.yml"), Path(".github/workflows/e2e.yml")):
        if p.exists():
            return yaml.safe_load(p.read_text())
    raise FileNotFoundError(".github/workflows/e2e.yml not found")


def _all_run_commands() -> list[str]:
    cmds: list[str] = []
    for job in _wf()["jobs"].values():
        for step in job.get("steps", []):
            if step.get("run"):
                cmds.append(step["run"])
    return cmds


def test_e2e_workflow_has_jobs() -> None:
    assert _wf()["jobs"], "e2e.yml must define at least one job"


def test_e2e_workflow_runs_api_lane() -> None:
    assert any("pytest e2e/api/" in c for c in _all_run_commands()), "missing the api lane step"


def test_e2e_workflow_runs_ui_lane() -> None:
    assert any("pytest e2e/ui/" in c for c in _all_run_commands()), "missing the ui lane step"


def test_e2e_workflow_runs_schemathesis() -> None:
    assert any("schemathesis" in c for c in _all_run_commands()), (
        "missing the schemathesis fuzz step"
    )


def test_e2e_workflow_runs_render_chart() -> None:
    assert any("test_render_chart" in c for c in _all_run_commands()), (
        "missing the /render/chart integration step (gated nowhere else)"
    )


def test_e2e_workflow_runs_a11y_lane() -> None:
    assert any("pytest e2e/a11y/" in c for c in _all_run_commands()), "missing the a11y lane gate"


def test_e2e_workflow_runs_ws_lane() -> None:
    assert any("pytest e2e/ws/" in c for c in _all_run_commands()), "missing the ws lane step"


def test_e2e_workflow_tears_down() -> None:
    assert any("down" in c for c in _all_run_commands()), "missing the compose teardown step"
