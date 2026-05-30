import pytest
from rest_framework.test import APIClient

from apps.thesis.models import Thesis


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_empty_ticker_returns_available_false(api):
    r = api.get("/api/analytics/track-record/")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ticker": "", "available": False, "record": None}


@pytest.mark.django_db
def test_empty_ticker_explicit_blank(api):
    r = api.get("/api/analytics/track-record/?ticker=")
    assert r.status_code == 200
    body = r.json()
    assert body == {"ticker": "", "available": False, "record": None}


@pytest.mark.django_db
def test_ticker_below_min_n_returns_available_false(api):
    # Only 2 closed theses — below the default min_n=3 threshold
    Thesis.objects.create(
        title="T1", ticker="AAPL", direction="bullish", conviction=3, status="closed_win"
    )
    Thesis.objects.create(
        title="T2", ticker="AAPL", direction="bullish", conviction=3, status="closed_loss"
    )

    r = api.get("/api/analytics/track-record/?ticker=AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["available"] is False
    assert body["record"] is None


@pytest.mark.django_db
def test_ticker_above_min_n_returns_available_true(api):
    # 4 closed theses: 3 wins, 1 loss
    Thesis.objects.create(
        title="T1", ticker="NVDA", direction="bullish", conviction=4, status="closed_win"
    )
    Thesis.objects.create(
        title="T2", ticker="NVDA", direction="bullish", conviction=4, status="closed_win"
    )
    Thesis.objects.create(
        title="T3", ticker="NVDA", direction="bullish", conviction=4, status="closed_win"
    )
    Thesis.objects.create(
        title="T4", ticker="NVDA", direction="bearish", conviction=2, status="closed_loss"
    )

    r = api.get("/api/analytics/track-record/?ticker=NVDA")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "NVDA"
    assert body["available"] is True
    record = body["record"]
    assert record is not None
    assert record["ticker"] == "NVDA"
    assert record["closed_n"] >= 3
    assert record["counts"]["win"] == 3


@pytest.mark.django_db
def test_ticker_is_uppercased(api):
    # Seed with uppercase ticker (model auto-uppercases on save)
    Thesis.objects.create(
        title="T1", ticker="TSLA", direction="bullish", conviction=3, status="closed_win"
    )
    Thesis.objects.create(
        title="T2", ticker="TSLA", direction="bullish", conviction=3, status="closed_win"
    )
    Thesis.objects.create(
        title="T3", ticker="TSLA", direction="bullish", conviction=3, status="closed_win"
    )

    # Pass lowercase in query param — endpoint must uppercase it
    r = api.get("/api/analytics/track-record/?ticker=tsla")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "TSLA"
    assert body["available"] is True


@pytest.mark.django_db
def test_bad_conviction_param_is_treated_as_none(api):
    # 3 closed theses to clear min_n
    Thesis.objects.create(
        title="T1", ticker="META", direction="bullish", conviction=3, status="closed_win"
    )
    Thesis.objects.create(
        title="T2", ticker="META", direction="bullish", conviction=3, status="closed_win"
    )
    Thesis.objects.create(
        title="T3", ticker="META", direction="bullish", conviction=3, status="closed_loss"
    )

    # "abc" is not a valid int — endpoint should silently treat it as None
    r = api.get("/api/analytics/track-record/?ticker=META&conviction=abc")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "META"
    assert body["available"] is True
