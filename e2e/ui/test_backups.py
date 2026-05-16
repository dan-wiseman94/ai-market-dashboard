"""Journey 6 — back up now, verify record + file + gzip magic bytes."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_BASE_URL, E2E_FRONTEND_URL


@pytest.mark.integration
def test_backup_roundtrip(page, tmp_path: Path) -> None:
    page.goto(f"{E2E_FRONTEND_URL}/settings/backups")
    page.get_by_role("button", name="Back up now ↻").click()

    expect(page.locator("tr:has-text('ok')")).to_be_visible(timeout=60000)

    rows = httpx.get(f"{E2E_BASE_URL}/api/backups/", timeout=5).json()
    rows = rows.get("results", rows)
    rec = next(r for r in rows if r["kind"] == "manual" and r["status"] == "ok")
    r = httpx.get(f"{E2E_BASE_URL}/api/backups/{rec['id']}/download/", timeout=30)
    dl = tmp_path / rec["filename"]
    dl.write_bytes(r.content)

    assert dl.stat().st_size > 0
    with dl.open("rb") as f:
        assert f.read(2) == b"\x1f\x8b"
