"""POST /api/triggers/backtest/ replays a DSL against stored OHLC bars."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def aapl_bars(db) -> None:
    from apps.market.models import OHLCBar

    base = datetime(2026, 3, 1, 14, 30, tzinfo=UTC)
    rows = []
    for i, close in enumerate([100, 101, 99, 105, 110, 108, 112, 115, 113, 120]):
        rows.append(
            OHLCBar(
                ticker="AAPL",
                timeframe="1d",
                ts=base + timedelta(days=i),
                open=close - 0.5,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1_000_000,
            )
        )
    OHLCBar.objects.bulk_create(rows)


def test_backtest_price_gt_threshold(db, aapl_bars) -> None:
    condition = {"all": [{"metric": "price", "ticker": "AAPL", "op": ">", "value": 108}]}
    client = APIClient()
    resp = client.post(
        "/api/triggers/backtest/",
        data={
            "condition": condition,
            "start": "2026-03-01",
            "end": "2026-03-15",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["match_count"] == 5  # closes at 110, 112, 115, 113, 120


def test_backtest_returns_timestamps(db, aapl_bars) -> None:
    condition = {"all": [{"metric": "price", "ticker": "AAPL", "op": ">=", "value": 115}]}
    client = APIClient()
    resp = client.post(
        "/api/triggers/backtest/",
        data={"condition": condition, "start": "2026-03-01", "end": "2026-03-15"},
        format="json",
    )
    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 2  # 115 and 120


def test_backtest_missing_condition_400(db) -> None:
    client = APIClient()
    resp = client.post(
        "/api/triggers/backtest/", data={"start": "2026-03-01", "end": "2026-03-10"}, format="json"
    )
    assert resp.status_code == 400


def test_backtest_bad_dates_400(db) -> None:
    client = APIClient()
    resp = client.post(
        "/api/triggers/backtest/",
        data={
            "condition": {"all": [{"metric": "price", "ticker": "AAPL", "op": ">", "value": 1}]},
            "start": "not-a-date",
            "end": "2026-03-10",
        },
        format="json",
    )
    assert resp.status_code == 400
