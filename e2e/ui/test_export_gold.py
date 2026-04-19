"""Journey 5 — start export, download, open zip, verify manifest."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import expect

from e2e.conftest import E2E_BASE_URL, E2E_FRONTEND_URL


@pytest.mark.integration
def test_export_roundtrip(page, tmp_path: Path) -> None:
    page.goto(f"{E2E_FRONTEND_URL}/settings/export")
    page.get_by_role("button", name="Start export").click()

    expect(page.locator("tr:has-text('done')")).to_be_visible(timeout=60000)

    jobs = httpx.get(f"{E2E_BASE_URL}/api/export/", timeout=5).json()
    rows = jobs.get("results", jobs)
    done = next(j for j in rows if j["status"] == "done")

    dl_path = tmp_path / done["filename"]
    r = httpx.get(f"{E2E_BASE_URL}/api/export/{done['id']}/download/", timeout=30)
    dl_path.write_bytes(r.content)

    with zipfile.ZipFile(dl_path) as zf:
        names = zf.namelist()
        assert any("manifest.json" in n for n in names)
        manifest_name = next(n for n in names if n.endswith("manifest.json"))
        manifest = json.loads(zf.read(manifest_name))
        assert manifest["version"] == 1
