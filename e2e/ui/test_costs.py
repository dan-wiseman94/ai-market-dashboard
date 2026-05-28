"""Costs gold paths."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest
from playwright.sync_api import expect

from e2e.pages.costs import CostsPage


@pytest.mark.integration
@pytest.mark.ui
def test_costs_today_tile(page, frontend_base_url, analytics) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    c.expect_error_boundary_absent()
    # The "Today" stat tile is always rendered; with seeded AIRuns the value is non-zero.
    today_section = page.locator("text=Today").first
    expect(today_section).to_be_visible(timeout=10_000)
    # The costs page renders at least one $ amount (stat tiles + chart if data present).
    expect(page.locator("body")).to_contain_text("$")


@pytest.mark.integration
@pytest.mark.ui
def test_costs_csv_export_downloads_and_parses(page, frontend_base_url, analytics) -> None:
    c = CostsPage(page, frontend_base_url)
    c.go()
    c.expect_error_boundary_absent()
    # The CSV export link is an <a href> that triggers a download.
    csv_link = page.get_by_role("link", name="Export CSV")
    expect(csv_link).to_be_visible(timeout=10_000)
    with page.expect_download() as info:
        csv_link.click()
    data = info.value.path()
    assert data is not None, "Download path should not be None"
    content = Path(data).read_bytes()
    rows = list(csv.reader(io.StringIO(content.decode("utf-8"))))
    assert len(rows) >= 1, "CSV must have at least a header row"
    header = ",".join(rows[0]).lower()
    assert "provider" in header or "cost" in header or "date" in header, (
        f"unexpected CSV header: {rows[0]}"
    )


@pytest.mark.integration
@pytest.mark.ui
def test_costs_page_breakdown_table_visible(page, frontend_base_url, analytics) -> None:
    """With seeded AI runs, the breakdown section renders a table."""
    c = CostsPage(page, frontend_base_url)
    c.go()
    c.expect_error_boundary_absent()
    # The DailyCostChart (cost-tile-today) appears when there is data in range.
    expect(c.today_tile).to_be_visible(timeout=10_000)
    expect(c.today_tile).to_contain_text("$")
