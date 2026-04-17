from unittest.mock import MagicMock, patch

import pytest

from apps.market.services.quotes import fetch_quotes
from apps.market import cache as cache_module


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis
    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


@pytest.mark.django_db
def test_fetch_quotes_uses_schwab_and_caches():
    # Schwab get_quotes returns a mapping: {"SPY": {...}, "QQQ": {...}}
    schwab_resp = MagicMock()
    schwab_resp.json.return_value = {
        "SPY": {"quote": {"lastPrice": 550.0, "bidPrice": 549.9, "askPrice": 550.1,
                          "totalVolume": 1000, "highPrice": 552, "lowPrice": 548, "netPercentChange": 0.5}},
        "QQQ": {"quote": {"lastPrice": 480.0, "bidPrice": 479.9, "askPrice": 480.1,
                          "totalVolume": 900, "highPrice": 482, "lowPrice": 478, "netPercentChange": 0.2}},
    }
    client = MagicMock()
    client.get_quotes.return_value = schwab_resp

    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        result = fetch_quotes(["SPY", "QQQ"])

    assert result["SPY"]["last"] == 550.0
    assert result["QQQ"]["last"] == 480.0
    client.get_quotes.assert_called_once_with(["QQQ", "SPY"])

    # Second call within TTL should NOT hit Schwab again
    with patch("apps.market.services.quotes.get_schwab_client", return_value=client):
        result2 = fetch_quotes(["SPY", "QQQ"])
    assert result2 == result
    assert client.get_quotes.call_count == 1  # still 1 from before


@pytest.mark.django_db
def test_fetch_quotes_empty_list():
    result = fetch_quotes([])
    assert result == {}
