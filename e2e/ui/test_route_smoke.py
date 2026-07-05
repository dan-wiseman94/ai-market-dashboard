"""Smoke coverage for routes that otherwise have no ui/visual/a11y test.

Each route is navigated with the lightest seed rung that lets it render
meaningfully, then asserted to (1) not fall into the ErrorBoundary and (2) show
its breadcrumb (AppLayout renders one per route via ``handle.crumb``). The
autouse console guard additionally fails the test on any console/5xx error, so
a route that 404s a fetch or throws surfaces here.

These are deliberately shallow — they catch "the route is broken/empty-crashes"
regressions across the strategy surface and other secondary pages. Richer
per-route flows live in their own files.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from e2e.pages.base import BasePage

# (path, highest seed rung the route needs). Param routes (warroom/:id,
# coverage/:ticker) are covered separately where their data is seeded.
ROUTES: list[tuple[str, str]] = [
    ("/settings/system", "minimal"),
    ("/settings/connections", "minimal"),
    ("/market-data", "market"),
    ("/snapshots", "snapshots"),
    ("/scorecard", "thesis"),
    ("/mirror", "thesis"),
    ("/regime", "minimal"),
    ("/book", "minimal"),
    ("/themes", "minimal"),
    ("/warroom", "minimal"),
    ("/desk", "minimal"),
    ("/portfolio", "thesis"),
    ("/theses/new", "minimal"),
    ("/recall", "minimal"),
    ("/errors", "minimal"),
]


@pytest.mark.integration
@pytest.mark.ui
@pytest.mark.parametrize("path,rung", ROUTES, ids=[r[0] for r in ROUTES])
def test_route_smoke(page, frontend_base_url, request, path, rung) -> None:
    request.getfixturevalue(rung)  # seed the live DB at the needed rung
    base = BasePage(page, frontend_base_url)
    base.goto(path)  # waits for the app shell to mount
    base.expect_error_boundary_absent()
    expect(base.breadcrumb_trail).to_be_visible()
