"""TradingView MCP connection — the mock OAuth flow end to end (MOCK_EXTERNAL overlay).

The authorize URL is the app's own callback with a canned code; following it ourselves
stands in for the browser. Everything else is the real code path over canned MCP results.
"""

from __future__ import annotations

import pytest

BASE = "/api/schwab/data-sources/tradingview"


@pytest.mark.integration
def test_tradingview_connect_test_toggle_disconnect(api_client, minimal) -> None:
    r = api_client.get(f"{BASE}/authorize/")
    assert r.status_code == 200
    url = r.json()["url"]
    assert "code=MOCK_OAUTH" in url

    r = api_client.get(f"{BASE}/callback/", params={"code": "MOCK_OAUTH", "state": "mock"})
    assert r.status_code == 302  # httpx does not follow redirects by default
    assert "tradingview=connected" in r.headers["location"]

    r = api_client.get("/api/schwab/data-sources/")
    assert r.status_code == 200
    tv = {d["provider"]: d for d in r.json()["data_sources"]}["tradingview"]
    assert tv["auth"] == "oauth" and tv["status"]["configured"] is True

    r = api_client.post(f"{BASE}/test/")
    assert r.status_code == 200
    assert r.json()["ok"] is True and "tools available" in r.json()["message"]

    r = api_client.patch("/api/settings/", json={"tradingview_tools_enabled": True})
    assert r.status_code == 200 and r.json()["tradingview_tools_enabled"] is True
    try:
        r = api_client.delete(f"{BASE}/")
        assert r.status_code == 200 and r.json()["configured"] is False
        r = api_client.get("/api/schwab/data-sources/")
        assert {d["provider"]: d for d in r.json()["data_sources"]}["tradingview"]["status"][
            "configured"
        ] is False
    finally:
        api_client.patch("/api/settings/", json={"tradingview_tools_enabled": None})


@pytest.mark.integration
def test_tradingview_callback_rejects_missing_code(api_client, minimal) -> None:
    r = api_client.get(f"{BASE}/callback/", params={"state": "mock"})
    assert r.status_code == 400
    assert r.json()["code"] == "missing_code"
