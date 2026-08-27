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
    """UI lane modules are importable.

    Each file should at least parse — actual journey wiring is exercised at
    collection time when pytest discovers tests.
    """
    # Explicit imports — no dynamic dispatch — so a deleted/renamed module
    # surfaces as an ImportError at collection time, not at runtime.
    from e2e.ui import (  # noqa: F401
        test_analytics,
        test_backups,
        test_compare,
        test_costs,
        test_dashboard,
        test_error_paths,
        test_export,
        test_keyboard_and_palette,
        test_observer,
        test_profiles,
        test_schwab_oauth,
        test_settings,
        test_snapshots,
        test_threads,
        test_triggers,
        test_watchlists,
    )


@pytest.mark.integration
def test_api_base_url_fixture(api_base_url: str) -> None:
    assert api_base_url.startswith("http://")


@pytest.mark.integration
def test_frontend_base_url_fixture(frontend_base_url: str) -> None:
    assert frontend_base_url.startswith("http://")
