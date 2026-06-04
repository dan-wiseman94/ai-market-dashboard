"""Invariant guard for config/urls.py include ordering.

CLAUDE.md landmine: specific ``/api/<prefix>/`` includes are registered **before**
the generic ``path("api/", include(...))`` catch-alls (profiles / snapshots /
threads / thesis).  A past regression reordered them and routed ``/api/costs/today``
into the wrong app.  URL resolution is first-match-wins and entirely silent when it
goes wrong — nothing errors, requests just land in the wrong view.

This pins the expected resolution for each specific prefix, so a reorder, a removed
include, or a new greedy pattern in a generic app turns red instead of mis-routing.
"""

import pytest
from django.urls import resolve


def _resolved_module(path: str) -> str:
    """Module that owns the view a path resolves to.

    Works for both function-based views (``func.__module__``) and class-based
    views, where Django/DRF stash the class on ``.view_class`` / ``.cls`` (the
    bare ``func`` would otherwise report the framework module)."""
    match = resolve(path)
    func = match.func
    view_class = getattr(func, "view_class", None) or getattr(func, "cls", None)
    target = view_class if view_class is not None else func
    return target.__module__


# (path, module-prefix the view MUST live under).  Every entry is a specific prefix
# that precedes the generic /api/ includes and could be swallowed by a reorder.
SPECIFIC_ROUTES = [
    ("/api/schema/", "drf_spectacular"),  # the schema endpoint the drift gate depends on
    ("/api/costs/today/", "apps.costs"),  # the documented past regression
    ("/api/observer/market-status/", "apps.observer"),
    ("/api/analytics/calibration/", "apps.analytics"),
    ("/api/market/quotes/", "apps.market"),
    ("/api/schwab/status/", "apps.secrets"),  # secrets app is mounted at /api/schwab/
    ("/api/aieval/runs/", "apps.aieval"),
    ("/api/predictions/ai-view/", "apps.predictions"),
]


@pytest.mark.parametrize("path,expected_prefix", SPECIFIC_ROUTES)
def test_specific_prefix_resolves_to_its_own_app(path, expected_prefix):
    module = _resolved_module(path)
    assert module.startswith(expected_prefix), (
        f"{path} resolved into {module!r}, not {expected_prefix!r} — a config/urls.py "
        "include-ordering regression (specific prefix swallowed by a generic /api/ include)"
    )
