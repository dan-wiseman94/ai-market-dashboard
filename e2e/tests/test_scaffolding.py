"""Scaffolding collection test — asserts new lane dirs are importable."""
from __future__ import annotations

import pytest


def test_lane_packages_importable() -> None:
    import e2e.a11y
    import e2e.api
    import e2e.helpers
    import e2e.mocks
    import e2e.perf
    import e2e.ui
    import e2e.visual
    import e2e.ws  # noqa: F401


def test_ui_journeys_importable() -> None:
    import importlib
    for mod in [
        "e2e.ui.test_snapshots_capture_gold",
        "e2e.ui.test_compare_two_branches_gold",
        "e2e.ui.test_observer_run_now_gold",
        "e2e.ui.test_trigger_fire_gold",
        "e2e.ui.test_backups_gold",
        "e2e.ui.test_export_gold",
    ]:
        importlib.import_module(mod)


@pytest.mark.integration
def test_api_base_url_fixture(api_base_url: str) -> None:
    assert api_base_url.startswith("http://")


@pytest.mark.integration
def test_frontend_base_url_fixture(frontend_base_url: str) -> None:
    assert frontend_base_url.startswith("http://")
