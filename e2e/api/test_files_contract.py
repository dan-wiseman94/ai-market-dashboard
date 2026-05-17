"""Files API — list shape; full upload tested in the UI lane."""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_files_list(api_client, minimal) -> None:
    r = api_client.get("/api/files/")
    assert r.status_code == 200
    body = r.json()
    rows = body if isinstance(body, list) else body.get("results", body)
    assert isinstance(rows, list)
