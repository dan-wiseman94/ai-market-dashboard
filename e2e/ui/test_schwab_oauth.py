"""Schwab OAuth gold paths via the scenario engine.

Under MOCK_EXTERNAL + schwab-oauth-ok the OAuth flow runs on canned mock data (no
real Schwab HTTP): authorize returns a stub URL; the callback exchanges a mock code
into an encrypted, persisted token.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
@pytest.mark.ui
def test_oauth_authorize_redirects_to_stub(api_client, minimal, scenario) -> None:
    scenario.use("schwab-oauth-ok")
    r = api_client.get("/api/schwab/authorize/")
    assert r.status_code == 200, r.text
    # The canned flow points at our own callback stub, not the real Schwab endpoint.
    assert "MOCK_OAUTH" in r.json()["url"]


@pytest.mark.integration
@pytest.mark.ui
def test_oauth_callback_persists_encrypted_token(api_client, minimal, scenario) -> None:
    scenario.use("schwab-oauth-ok")
    r = api_client.get("/api/schwab/callback/", params={"code": "MOCK_OAUTH"})
    assert r.status_code in (302, 200), r.text
    if r.status_code == 302:
        assert "schwab=connected" in r.headers.get("location", "")
    # Status now reports connected — the encrypted token round-trips out of the DB.
    assert api_client.get("/api/schwab/status/").json()["connected"] is True
