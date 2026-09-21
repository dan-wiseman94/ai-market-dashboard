"""Browse + rollup surface for the Prediction Ledger: GET /api/predictions/,
/api/predictions/<id>/ and /api/predictions/stats/.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.observer.models import AIPrediction
from apps.profiles.models import TradingProfile


def _pred(ticker="SPY", *, direction="bullish", status="open", horizon=7, age_days=0, **kw):
    predicted_at = timezone.now() - timedelta(days=age_days)
    return AIPrediction.objects.create(
        ticker=ticker,
        direction=direction,
        horizon_days=horizon,
        confidence=kw.pop("confidence", 0.7),
        provider=kw.pop("provider", "claude"),
        model=kw.pop("model", "claude-opus-5"),
        predicted_at=predicted_at,
        resolve_at=predicted_at + timedelta(days=horizon),
        status=status,
        **kw,
    )


@pytest.mark.django_db
def test_list_is_paginated_newest_first(api):
    older = _pred("AAPL", age_days=3)
    newer = _pred("NVDA", age_days=1)
    body = api.get("/api/predictions/").json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 2
    assert [r["id"] for r in body["results"]] == [newer.id, older.id]


@pytest.mark.django_db
def test_list_row_carries_the_full_call_and_its_score(api):
    profile = TradingProfile.objects.create(name="Swing", style="s")
    p = _pred(
        "NVDA",
        direction="bearish",
        status="resolved",
        horizon=30,
        profile=profile,
        confidence=0.62,
        expected_move_pct=0.05,
        rationale="lower highs",
        invalidation_price=Decimal("150.0000"),
        invalidation_note="reclaims 150",
        forward_return_pct=-4.2,
        verdict="correct",
        resolved_at=timezone.now(),
    )
    row = api.get("/api/predictions/").json()["results"][0]
    assert row["id"] == p.id
    assert row["ticker"] == "NVDA"
    assert row["direction"] == "bearish"
    assert row["horizon_days"] == 30
    assert row["confidence"] == 0.62
    assert row["expected_move_pct"] == 0.05
    assert row["rationale"] == "lower highs"
    assert row["invalidation_note"] == "reclaims 150"
    assert row["status"] == "resolved"
    assert row["verdict"] == "correct"
    assert row["forward_return_pct"] == -4.2
    assert row["profile_id"] == profile.id
    assert row["profile_name"] == "Swing"
    assert row["source_snapshot_id"] is None


@pytest.mark.django_db
def test_list_filters_by_ticker_status_and_horizon(api):
    _pred("SPY", status="open", horizon=7)
    _pred("SPY", status="invalidated", horizon=30)
    _pred("QQQ", status="open", horizon=30)

    assert api.get("/api/predictions/?ticker=spy").json()["count"] == 2
    assert api.get("/api/predictions/?status=invalidated").json()["count"] == 1
    assert api.get("/api/predictions/?horizon=30").json()["count"] == 2
    assert api.get("/api/predictions/?ticker=SPY&horizon=30").json()["count"] == 1


@pytest.mark.django_db
def test_list_ignores_junk_filters_rather_than_400ing(api):
    _pred("SPY")
    assert api.get("/api/predictions/?status=banana&horizon=abc").json()["count"] == 1


@pytest.mark.django_db
def test_detail_returns_one_row(api):
    p = _pred("SPY")
    r = api.get(f"/api/predictions/{p.id}/")
    assert r.status_code == 200
    assert r.json()["id"] == p.id
    assert api.get("/api/predictions/999999/").status_code == 404


@pytest.mark.django_db
def test_stats_rolls_up_hit_rate_overall_and_per_ticker(api):
    _pred("SPY", status="resolved", verdict="correct", forward_return_pct=2.0)
    _pred("SPY", status="resolved", verdict="incorrect", forward_return_pct=-1.0, horizon=30)
    _pred("SPY", status="resolved", verdict="inconclusive", horizon=90)
    _pred("NVDA", status="resolved", verdict="correct", forward_return_pct=6.0)
    _pred("NVDA", status="open")

    body = api.get("/api/predictions/stats/").json()
    totals = body["totals"]
    assert totals["total"] == 5
    assert totals["open"] == 1
    assert totals["resolved"] == 4
    assert totals["correct"] == 2
    assert totals["incorrect"] == 1
    assert totals["inconclusive"] == 1
    # inconclusive is not scored either way: 2/(2+1)
    assert totals["hit_rate"] == round(2 / 3, 4)

    by_ticker = {row["ticker"]: row for row in body["by_ticker"]}
    assert by_ticker["SPY"]["total"] == 3
    assert by_ticker["SPY"]["hit_rate"] == 0.5
    assert by_ticker["NVDA"]["hit_rate"] == 1.0
    assert by_ticker["NVDA"]["avg_forward_return_pct"] == 6.0


@pytest.mark.django_db
def test_stats_hit_rate_is_none_without_a_decisive_call(api):
    _pred("SPY", status="open")
    body = api.get("/api/predictions/stats/").json()
    assert body["totals"]["hit_rate"] is None
    assert body["totals"]["avg_forward_return_pct"] is None
    assert body["by_ticker"][0]["hit_rate"] is None


@pytest.mark.django_db
def test_stats_honors_the_list_filters_and_echoes_them(api):
    _pred("SPY", status="resolved", verdict="correct")
    _pred("NVDA", status="resolved", verdict="incorrect")
    body = api.get("/api/predictions/stats/?ticker=SPY").json()
    assert body["filters"] == {"ticker": "SPY", "status": None, "horizon": None}
    assert body["totals"]["total"] == 1
    assert [row["ticker"] for row in body["by_ticker"]] == ["SPY"]


@pytest.mark.django_db
def test_stats_is_query_bounded(api, django_assert_max_num_queries):
    """The per-ticker rollup aggregates in the DB — it must not fan out one query
    per ticker as the ledger grows."""
    for i in range(12):
        _pred(f"TK{i}", status="resolved", verdict="correct", forward_return_pct=1.0)
    with django_assert_max_num_queries(4):
        assert api.get("/api/predictions/stats/").status_code == 200
