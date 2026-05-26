"""Journey 6 — back up now, verify record + file + gzip magic bytes."""

from __future__ import annotations

import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_BASE_URL, E2E_FRONTEND_URL


def _poll_for_ok_backup(timeout_s: int = 60) -> dict:
    """Poll the API until a manual ok-status backup appears."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        rows = httpx.get(f"{E2E_BASE_URL}/api/backups/", timeout=5).json()
        rows = rows.get("results", rows)
        for r in rows:
            if r["kind"] == "manual" and r["status"] == "ok":
                return r
        time.sleep(1)
    raise AssertionError("no manual ok-status backup within timeout")


@pytest.mark.integration
@pytest.mark.ui
def test_backup_roundtrip(page, tmp_path: Path) -> None:
    page.goto(f"{E2E_FRONTEND_URL}/settings/backups")
    page.get_by_role("button", name="Back up now").click()

    # The frontend's React Query doesn't refetchInterval — wait via the API for
    # the worker to finish pg_dump, then reload the page so the UI re-fetches.
    rec = _poll_for_ok_backup()
    page.reload()
    expect(page.locator(f"[data-testid='backup-row-{rec['id']}']")).to_be_visible(timeout=10_000)

    r = httpx.get(f"{E2E_BASE_URL}/api/backups/{rec['id']}/download/", timeout=30)
    dl = tmp_path / rec["filename"]
    dl.write_bytes(r.content)
    assert dl.stat().st_size > 0
    # pg_dump -Fc produces "PGDMP" custom-format magic; -Fp | gzip would
    # produce \x1f\x8b. Accept either so the test stays correct as the format
    # evolves.
    magic = dl.open("rb").read(5)
    assert magic.startswith((b"PGDMP", b"\x1f\x8b")), f"unexpected magic: {magic!r}"
