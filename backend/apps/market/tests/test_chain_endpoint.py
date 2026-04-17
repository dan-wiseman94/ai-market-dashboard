from unittest.mock import patch

import pytest
from django.test import Client


@pytest.mark.django_db
def test_chain_endpoint_returns_payload():
    payload = {"underlying_last": "521.30", "expiries": {"2026-04-25": {"calls": [], "puts": []}}}
    with patch("apps.market.views.fetch_chain", return_value=payload):
        resp = Client().get("/api/market/chain/?ticker=SPY")
    assert resp.status_code == 200
    body = resp.json()
    assert body["underlying_last"] == "521.30"
    assert "2026-04-25" in body["expiries"]


@pytest.mark.django_db
def test_chain_endpoint_missing_ticker_returns_400():
    resp = Client().get("/api/market/chain/")
    assert resp.status_code == 400
    assert resp.json()["code"] == "missing_ticker"
