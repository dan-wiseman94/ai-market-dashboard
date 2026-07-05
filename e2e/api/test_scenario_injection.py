"""Service error-injection scenarios surface through the real API (api lane).

The scenario is selected via the X-E2E-Scenario header on the httpx client; the
backend service clients consume it and turn it into real behavior.

Note: schwab-401's effect on capture is covered at the backend level
(apps/snapshots/tests/test_capture_scenario.py) because the schwab data path is
Redis-cached and the cache can't be cleared from this lane; the news-503 partial
failure is covered in e2e/ui/test_snapshots.py.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_files_upload_fail_rejects_upload(api_client, minimal) -> None:
    api_client.headers["X-E2E-Scenario"] = "files-upload-fail"
    r = api_client.post(
        "/api/files/",
        files={"file": ("probe.txt", b"hello", "text/plain")},
    )
    # The injected provider error must surface as a failed upload, never a 201.
    assert r.status_code != 201, r.text
    assert r.status_code >= 400, r.text
