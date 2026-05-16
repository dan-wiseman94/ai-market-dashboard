"""Guards that the scenario engine is invisible when MOCK_EXTERNAL=false.

Runs from the API lane. When the e2e overlay is up (``MOCK_EXTERNAL=true``) this
test is skipped — its premise is "what would prod look like" — and the actual
prod posture is verified only when the test is invoked against a non-overlay
stack.
"""

from __future__ import annotations

import os

import httpx
import pytest


@pytest.mark.integration
def test_scenario_probe_404_when_mock_external_false(api_base_url) -> None:
    if os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true", "yes"):
        pytest.skip("e2e overlay is up; this assertion only applies to prod posture")

    r = httpx.get(
        f"{api_base_url}/api/_scenario_probe/",
        headers={"X-E2E-Scenario": "claude-5xx"},
        timeout=3,
    )
    # Endpoint shouldn't exist without MOCK_EXTERNAL.
    assert r.status_code == 404


@pytest.mark.integration
def test_scenario_header_is_noop_when_mock_external_false(api_base_url) -> None:
    if os.environ.get("MOCK_EXTERNAL", "").lower() in ("1", "true", "yes"):
        pytest.skip("e2e overlay is up; this assertion only applies to prod posture")

    # Hit the readiness probe with the header — it should be ignored.
    r = httpx.get(
        f"{api_base_url}/api/ready/",
        headers={"X-E2E-Scenario": "claude-5xx"},
        timeout=3,
    )
    assert r.status_code in (200, 503)  # health depends on db/redis
