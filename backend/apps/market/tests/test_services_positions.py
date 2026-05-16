from unittest.mock import MagicMock, patch

import pytest

from apps.market import cache as cache_module
from apps.market.services.positions import fetch_positions


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    import fakeredis

    r = fakeredis.FakeRedis()
    monkeypatch.setattr(cache_module, "_redis", lambda: r)
    return r


@pytest.mark.django_db
def test_fetch_positions_extracts_from_account():
    # schwab-py returns a list from get_accounts with fields=positions
    hash_resp = MagicMock()
    hash_resp.json.return_value = [{"accountNumber": "111", "hashValue": "HASH1"}]

    accounts_resp = MagicMock()
    accounts_resp.json.return_value = [
        {
            "securitiesAccount": {
                "positions": [
                    {
                        "instrument": {"symbol": "NVDA"},
                        "longQuantity": 100,
                        "shortQuantity": 0,
                        "averagePrice": 800.0,
                        "marketValue": 85000.0,
                        "currentDayProfitLoss": 250.0,
                        "longOpenProfitLoss": 4950.0,
                    },
                    {
                        "instrument": {"symbol": "SPY"},
                        "longQuantity": 50,
                        "shortQuantity": 0,
                        "averagePrice": 540.0,
                        "marketValue": 27500.0,
                        "currentDayProfitLoss": 100.0,
                        "longOpenProfitLoss": 500.0,
                    },
                ]
            }
        }
    ]

    client = MagicMock()
    client.get_account_numbers.return_value = hash_resp
    client.get_accounts.return_value = accounts_resp

    with patch("apps.market.services.positions.get_schwab_client", return_value=client):
        positions = fetch_positions()

    assert len(positions) == 2
    nvda = next(p for p in positions if p["ticker"] == "NVDA")
    assert nvda["qty"] == 100
    assert nvda["avg_cost"] == 800.0
    assert nvda["unrealized_pl"] == 4950.0
    assert nvda["day_pl"] == 250.0
