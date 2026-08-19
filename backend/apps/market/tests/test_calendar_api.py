import pytest
from freezegun import freeze_time
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_create_and_list_override():
    c = APIClient()
    r = c.post(
        "/api/market/calendar-overrides/", {"ticker": "spy", "market_key": "crypto"}, format="json"
    )
    assert r.status_code == 201
    assert r.json()["ticker"] == "SPY"
    assert "symbol" not in r.json()  # API field is "ticker"; "symbol" is the DB column only
    r2 = c.get("/api/market/calendar-overrides/")
    assert any(row["ticker"] == "SPY" for row in r2.json())


@pytest.mark.django_db
def test_calendar_override_case_variant_duplicate_returns_400_not_500():
    """The symbol column (API field "ticker") is unique AND normalized (strip().upper())
    in Model.save() — AFTER the serializer's UniqueValidator runs on the *raw* value. So a
    case-variant of an existing ticker slips past validation and would 500 on the DB unique
    constraint (a schemathesis-found IntegrityError). It must be a clean 400, not a server
    error."""
    c = APIClient()
    r1 = c.post(
        "/api/market/calendar-overrides/", {"ticker": "SPY", "market_key": "crypto"}, format="json"
    )
    assert r1.status_code == 201, r1.content
    # "spy" collides with the already-stored "SPY" only at Model.save() time:
    r2 = c.post(
        "/api/market/calendar-overrides/", {"ticker": "spy", "market_key": "crypto"}, format="json"
    )
    assert r2.status_code == 400, r2.content
    assert "ticker" in r2.json()


@pytest.mark.django_db
def test_reject_unknown_market_key():
    c = APIClient()
    r = c.post(
        "/api/market/calendar-overrides/", {"ticker": "X", "market_key": "mars"}, format="json"
    )
    assert r.status_code == 400


@pytest.mark.django_db
@freeze_time("2026-04-18 14:00:00")  # Saturday
def test_calendar_status_for_tickers():
    c = APIClient()
    r = c.get("/api/market/calendar-status/?tickers=BTC-USD,SPY")
    assert r.status_code == 200
    markets = r.json()["markets"]
    assert markets["crypto"]["is_open"] is True
    assert markets["us_equity"]["is_open"] is False
