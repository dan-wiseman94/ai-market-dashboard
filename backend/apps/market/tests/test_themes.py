"""Theme narrative health: breadth, leadership, relative strength + CRUD."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.market.models import OHLCBar, Theme
from apps.market.services.themes import theme_health


def _bar(ticker, close, ts):
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1d",
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
        ts=ts,
    )


@pytest.mark.django_db
def test_theme_health_breadth_leadership_relative_strength():
    now = timezone.now()
    start = now - timedelta(days=20)
    for t, c0, c1 in [("AAPL", 100, 110), ("MSFT", 100, 95), ("$SPX", 100, 102)]:
        _bar(t, c0, start)
        _bar(t, c1, now)
    theme = Theme.objects.create(name="Big Tech", tickers=["AAPL", "MSFT"])

    h = theme_health(theme, window_days=20, now=now)
    assert h["breadth"] == pytest.approx(0.5)  # AAPL up, MSFT down
    assert h["mean_return_pct"] == pytest.approx(2.5)  # (+10 + -5)/2
    assert h["relative_strength"] == pytest.approx(0.5)  # 2.5 - SPX 2.0
    assert h["leadership"]["leader"]["ticker"] == "AAPL"
    assert h["leadership"]["laggard"]["ticker"] == "MSFT"
    assert h["coverage"] == {"priced": 2, "total": 2}


@pytest.mark.django_db
def test_theme_health_honest_when_no_prices():
    theme = Theme.objects.create(name="Obscure", tickers=["ZZZZ", "YYYY"])
    h = theme_health(theme, window_days=20)
    assert h["breadth"] is None
    assert h["coverage"]["priced"] == 0


@pytest.mark.django_db
def test_theme_crud_uppercases_and_health_endpoint():
    c = APIClient()
    r = c.post("/api/themes/", {"name": "AI-capex", "tickers": ["nvda", "amd"]}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["tickers"] == ["NVDA", "AMD"]  # upper-cased on save
    tid = r.json()["id"]
    h = c.get(f"/api/themes/{tid}/health/")
    assert h.status_code == 200
    assert "breadth" in h.json() and "members" in h.json()
