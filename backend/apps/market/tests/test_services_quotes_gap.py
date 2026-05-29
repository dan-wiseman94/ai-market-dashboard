from unittest.mock import MagicMock, patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.quotes import fetch_quotes


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


def _schwab_resp(quote_extra: dict, regular: dict | None = None):
    resp = MagicMock()
    blob = {
        "quote": {
            "lastPrice": 100.0,
            "bidPrice": 99.9,
            "askPrice": 100.1,
            "totalVolume": 1000,
            "highPrice": 101.0,
            "lowPrice": 99.0,
            "netPercentChange": 0.5,
            **quote_extra,
        }
    }
    if regular is not None:
        blob["regular"] = regular
    resp.json.return_value = {"SPY": blob}
    return resp


@pytest.mark.django_db
def test_gap_context_adds_prior_close_and_gap_pct():
    client = MagicMock()
    client.get_quotes.return_value = _schwab_resp(
        {"closePrice": 98.0, "mark": 100.05, "securityStatus": "Normal"},
        regular={"regularMarketLastPrice": 98.5},
    )
    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        out = fetch_quotes(["SPY"], gap_context=True)
    q = out["SPY"]
    assert q["prior_close"] == 98.0
    assert q["regular_last"] == 98.5
    assert q["mark"] == 100.05
    assert q["security_status"] == "Normal"
    assert round(q["gap_pct"], 2) == 2.04  # (100-98)/98*100


@pytest.mark.django_db
def test_gap_context_tolerates_missing_fields():
    client = MagicMock()
    client.get_quotes.return_value = _schwab_resp({})  # no closePrice/regular block
    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        out = fetch_quotes(["SPY"], gap_context=True)
    q = out["SPY"]
    assert q["prior_close"] is None
    assert q["gap_pct"] is None
    assert q["regular_last"] is None


@pytest.mark.django_db
def test_default_quotes_unchanged_no_gap_keys():
    client = MagicMock()
    client.get_quotes.return_value = _schwab_resp({"closePrice": 98.0})
    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        out = fetch_quotes(["SPY"])  # gap_context defaults False
    assert set(out["SPY"]) == {"last", "bid", "ask", "volume", "high", "low", "pct_change"}
