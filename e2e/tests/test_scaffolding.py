"""Scaffolding collection test — asserts new lane dirs are importable."""
from __future__ import annotations


def test_lane_packages_importable() -> None:
    import e2e.ui  # noqa: F401
    import e2e.api  # noqa: F401
    import e2e.ws  # noqa: F401
    import e2e.visual  # noqa: F401
    import e2e.a11y  # noqa: F401
    import e2e.perf  # noqa: F401
    import e2e.mocks  # noqa: F401
    import e2e.helpers  # noqa: F401


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
