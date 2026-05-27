from datetime import timedelta

import pytest
from django.utils import timezone

from apps.market.models import MarketEvent


@pytest.fixture
def api():
    from rest_framework.test import APIClient

    return APIClient()


@pytest.mark.django_db
def test_events_endpoint_returns_upcoming(api):
    MarketEvent.objects.create(
        source="finnhub",
        external_id="EARN:NVDA:x",
        kind="earnings",
        ticker="NVDA",
        title="NVDA earnings",
        event_time=timezone.now() + timedelta(days=3),
    )
    r = api.get("/api/market/events/?tickers=NVDA&within_days=14")
    assert r.status_code == 200
    body = r.json()
    assert body["earnings"][0]["ticker"] == "NVDA"
    assert "macro" in body


@pytest.mark.django_db
def test_events_endpoint_macro_toggle(api):
    MarketEvent.objects.create(
        source="s",
        external_id="CPI:z",
        kind="cpi",
        title="CPI",
        event_time=timezone.now() + timedelta(days=2),
    )
    r = api.get("/api/market/events/?include_macro=false")
    assert r.json()["macro"] == []


@pytest.mark.django_db
def test_events_endpoint_invalid_within_days(api):
    r = api.get("/api/market/events/?within_days=abc")
    assert r.status_code == 400
