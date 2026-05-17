"""Journey 5 — start export, download, open zip, verify manifest."""

from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_BASE_URL, E2E_FRONTEND_URL


def _poll_for_done_export(timeout_s: int = 60) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        jobs = httpx.get(f"{E2E_BASE_URL}/api/export/", timeout=5).json()
        rows = jobs.get("results", jobs)
        for j in rows:
            if j["status"] == "done":
                return j
        time.sleep(1)
    raise AssertionError("no done-status export within timeout")


@pytest.mark.integration
@pytest.mark.ui
def test_export_roundtrip(page, tmp_path: Path) -> None:
    page.goto(f"{E2E_FRONTEND_URL}/settings/export")
    page.get_by_role("button", name="Start export").click()

    done = _poll_for_done_export()
    page.reload()
    expect(page.locator(f"[data-testid='export-row-{done['id']}']")).to_be_visible(timeout=10_000)

    dl_path = tmp_path / done["filename"]
    r = httpx.get(f"{E2E_BASE_URL}/api/export/{done['id']}/download/", timeout=30)
    dl_path.write_bytes(r.content)

    with zipfile.ZipFile(dl_path) as zf:
        names = zf.namelist()
        assert any("manifest.json" in n for n in names)
        manifest_name = next(n for n in names if n.endswith("manifest.json"))
        manifest = json.loads(zf.read(manifest_name))
        assert manifest["version"] == 1
