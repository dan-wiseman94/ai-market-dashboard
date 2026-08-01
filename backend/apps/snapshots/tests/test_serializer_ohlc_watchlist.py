"""Rendering of per-watchlist-ticker daily history inside the OHLC section,
and its budget behavior: the enrichment is sacrificed before the primary
series loses any bars."""

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _render_ohlc, serialize_for_ai


def _bar(i: int, volume) -> dict:
    return {
        "ts": f"2026-07-{(i % 27) + 1:02d}T04:00:00+00:00",
        "open": 100 + i,
        "high": 101 + i,
        "low": 99 + i,
        "close": 100.5 + i,
        "volume": volume,
    }


def test_watchlist_daily_rendered_as_subsections_with_per_group_volume():
    out = _render_ohlc(
        {
            "ticker": "$SPX",
            "timeframe": "1m",
            "window": "24h",
            "bars": [_bar(0, 0)],
            "watchlist_daily": {"QQQ": [_bar(0, 100)], "$DJI": [_bar(0, 0)]},
        }
    )
    assert "### QQQ — daily" in out
    assert "### $DJI — daily" in out
    qqq_block = out.split("### QQQ — daily")[1].split("###")[0]
    dji_block = out.split("### $DJI — daily")[1].split("###")[0]
    assert "ts,open,high,low,close,volume" in qqq_block  # ETF keeps volume
    assert "ts,open,high,low,close,volume" not in dji_block  # index omits it


@pytest.mark.django_db
def test_budget_drops_watchlist_daily_before_primary_bars():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["ohlc"], source="manual")
    primary = [_bar(i, 1000) for i in range(30)]
    daily = {t: [_bar(i, 500) for i in range(100)] for t in ("AAA", "BBB", "CCC", "DDD")}
    SnapshotSection.objects.create(
        snapshot=s,
        kind="ohlc",
        status="done",
        payload={
            "ticker": "SPY",
            "timeframe": "1m",
            "window": "24h",
            "bars": primary,
            "watchlist_daily": daily,
        },
    )
    out = serialize_for_ai(s, max_tokens=6000)
    assert "watchlist daily history omitted" in out
    assert primary[-1]["ts"] in out  # primary series intact
    assert "older bars trimmed" not in out
    assert "### AAA" not in out
