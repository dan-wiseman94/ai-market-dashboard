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


@pytest.mark.django_db
def test_fetch_quotes_normalizes_index_aliases():
    # A bare "SPX" must reach Schwab as the "$SPX" index symbol, otherwise
    # Schwab returns nothing and the section comes back silently empty.
    schwab_resp = MagicMock()
    schwab_resp.json.return_value = {"$SPX": {"quote": {"lastPrice": 6000.0}}}
    client = MagicMock()
    client.get_quotes.return_value = schwab_resp

    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        result = fetch_quotes(["SPX"])

    client.get_quotes.assert_called_once_with(["$SPX"])
    assert result["$SPX"]["last"] == 6000.0


@pytest.mark.django_db
def test_fetch_quotes_nulls_placeholder_zero_high_low():
    # Before the day session Schwab reports highPrice/lowPrice as 0.0 — a
    # literal "Low 0.00" in the AI table reads as a crash, not a placeholder.
    schwab_resp = MagicMock()
    schwab_resp.json.return_value = {
        "QQQ": {
            "quote": {
                "lastPrice": 703.7,
                "bidPrice": 703.68,
                "askPrice": 703.72,
                "totalVolume": 1_834_178,
                "highPrice": 0.0,
                "lowPrice": 0.0,
                "netPercentChange": -0.74,
            }
        },
    }
    client = MagicMock()
    client.get_quotes.return_value = schwab_resp

    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        result = fetch_quotes(["QQQ"])

    assert result["QQQ"]["high"] is None
    assert result["QQQ"]["low"] is None
    assert result["QQQ"]["last"] == 703.7


@pytest.mark.django_db
def test_fetch_quotes_computes_futures_pct_change_from_close():
    # Futures quotes carry no netPercentChange; fall back to futurePercentChange,
    # then to (last - closePrice) / closePrice.
    schwab_resp = MagicMock()
    schwab_resp.json.return_value = {
        "/NQU26": {
            "quote": {
                "lastPrice": 29093.0,
                "bidPrice": 29093.0,
                "askPrice": 29094.0,
                "totalVolume": 110_708,
                "highPrice": 29337.0,
                "lowPrice": 28952.0,
                "closePrice": 29314.0,
            }
        },
        "/ESU26": {
            "quote": {
                "lastPrice": 7525.25,
                "futurePercentChange": -0.42,
                "closePrice": 7557.0,
            }
        },
    }
    client = MagicMock()
    client.get_quotes.return_value = schwab_resp

    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        result = fetch_quotes(["/NQU26", "/ESU26"])

    assert result["/NQU26"]["pct_change"] == pytest.approx((29093.0 - 29314.0) / 29314.0 * 100)
    assert result["/ESU26"]["pct_change"] == -0.42  # provider field wins over computed
    # Genuine intraday extremes are preserved.
    assert result["/NQU26"]["high"] == 29337.0
    assert result["/NQU26"]["low"] == 28952.0


@pytest.mark.django_db
def test_fetch_quotes_skips_error_envelope():
    # Schwab returns a top-level {"errors": {...}} envelope for unknown symbols;
    # it must not be rendered as a phantom "errors" ticker row.
    schwab_resp = MagicMock()
    schwab_resp.json.return_value = {
        "AAPL": {"quote": {"lastPrice": 200.0}},
        "errors": {"invalidSymbols": ["BOGUS"]},
    }
    client = MagicMock()
    client.get_quotes.return_value = schwab_resp

    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        result = fetch_quotes(["AAPL", "BOGUS"])

    assert "errors" not in result
    assert result["AAPL"]["last"] == 200.0
