"""Invariant guard: GET /api/dashboard/ survives *total* section failure with a
full, contract-valid payload.

CLAUDE.md landmine: each dashboard section is wrapped by ``_safe(fn, default)``,
and the defaults MUST be full contract-valid shapes — a bare ``{}`` default crashes
the SPA tile that reads e.g. ``triggers.latest_firings.length`` or maps over
``regime.drivers``.  The existing per-section tests cover theses/observer/triggers;
this guards *all eight* sections at once, so a newly added section with a thin
default (or a regression to ``{}``) turns red here instead of in the browser.
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import patch

import pytest

# Every section helper in apps.analytics.dashboard, and the shape its default must keep.
SECTION_HELPERS = [
    "_theses_section",
    "_events_section",
    "_observer_summary",
    "_triggers_summary",
    "_latest_briefing_summary",
    "_regime_section",
    "_book_section",
    "_desk_section",
]


def _assert_full_contract(body: dict) -> None:
    """Assert every key the frontend dereferences is present with the right type.
    List-typed fields are called with ``.length`` / ``.map`` in the SPA, so an
    absent key or wrong type is a crash, not a graceful empty."""
    assert isinstance(body["theses"], list)

    assert isinstance(body["events"], dict)
    assert isinstance(body["events"]["earnings"], list)
    assert isinstance(body["events"]["macro"], list)

    assert isinstance(body["observer"], dict)
    assert {"enabled_schedules", "runs_today"} <= body["observer"].keys()

    assert isinstance(body["triggers"], dict)
    assert "armed_count" in body["triggers"]
    assert isinstance(body["triggers"]["latest_firings"], list)

    assert body["briefing"] is None or isinstance(body["briefing"], dict)

    assert isinstance(body["regime"], dict)
    assert {"composite", "as_of"} <= body["regime"].keys()
    assert isinstance(body["regime"]["drivers"], list)

    assert isinstance(body["book"], dict)
    assert {"hhi", "alignment", "as_of"} <= body["book"].keys()

    assert isinstance(body["desk"], dict)
    assert {"unread", "latest"} <= body["desk"].keys()


@pytest.mark.django_db
def test_all_sections_down_still_returns_full_contract_shape(api):
    with ExitStack() as stack:
        for name in SECTION_HELPERS:
            stack.enter_context(
                patch(f"apps.analytics.dashboard.{name}", side_effect=RuntimeError("section down"))
            )
        r = api.get("/api/dashboard/")

    assert r.status_code == 200, "endpoint must never 500 even with every section down"
    _assert_full_contract(r.json())
