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


# ---------------------------------------------------------------------------
# Forward-return scoring fixtures and tests
#
# We seed 10 consecutive trading-day bars for MSFT at 20:00 UTC (the NYSE
# session-close time used by session_close_on / nearest_bar_close_within).
# This ensures trading_day_forward_return_pct finds the right bars within its
# 12h tolerance window.
#
# Dates:  May4(idx0), May5(idx1), May6(idx2), May7(idx3), May8(idx4),
#         May11(idx5), May12(idx6), May13(idx7), May14(idx8), May15(idx9)
# Closes: 100, 101, 103, 106, 104, 107, 108, 108, 109, 110
#
# Condition: price > 102  → matches days 2-9 (closes 103,106,104,107,108,108,109,110)
#
# Forward targets (calendar-computed; verified via add_trading_days):
#   day2 (May6) fwd1→May7(idx3=106)   fwd5→May13(idx7=108)
#   day3 (May7) fwd1→May8(idx4=104)   fwd5→May14(idx8=109)
#   day4 (May8) fwd1→May11(idx5=107)  fwd5→May15(idx9=110)
#   day5 (May11) fwd1→May12(idx6=108) fwd5→May18(no bar)→None
#   day6 (May12) fwd1→May13(idx7=108) fwd5→May19(no bar)→None
#   day7 (May13) fwd1→May14(idx8=109) fwd5→May20(no bar)→None
#   day8 (May14) fwd1→May15(idx9=110) fwd5→May21(no bar)→None
#   day9 (May15) fwd1→May18(no bar)→None fwd5→None
#
# Hand-computed returns (using _pct_change = (t1-t0)/t0 * 100):
#   day2: fwd1= (106-103)/103*100 ≈ +2.9126   fwd5=(108-103)/103*100 ≈ +4.8544
#   day3: fwd1= (104-106)/106*100 ≈ -1.8868   fwd5=(109-106)/106*100 ≈ +2.8302
#   day4: fwd1= (107-104)/104*100 ≈ +2.8846   fwd5=(110-104)/104*100 ≈ +5.7692
#   day5: fwd1= (108-107)/107*100 ≈ +0.9346   fwd5=None
#   day6: fwd1= (108-108)/108*100 =   0.0     fwd5=None
#   day7: fwd1= (109-108)/108*100 ≈ +0.9259   fwd5=None
#   day8: fwd1= (110-109)/109*100 ≈ +0.9174   fwd5=None
#   day9: fwd1=None                            fwd5=None
#
# scored_1d=7, positive 1d: days 2,4,5,7,8 → 5/7 = 0.7143
# scored_5d=3, positive 5d: days 2,3,4     → 3/3 = 1.0
# avg_fwd_1d_pct = round(mean(scored_1d), 4) = 0.9555
# avg_fwd_5d_pct = round(mean(scored_5d), 4) = 4.4846
# ---------------------------------------------------------------------------

# 10 trading days: Mon-Fri May4-8, Mon-Fri May11-15, 2026
_MSFT_TRADING_DAYS = [
    datetime(2026, 5, 4, 20, 0, tzinfo=UTC),  # idx 0 — Mon
    datetime(2026, 5, 5, 20, 0, tzinfo=UTC),  # idx 1 — Tue
    datetime(2026, 5, 6, 20, 0, tzinfo=UTC),  # idx 2 — Wed (first match)
    datetime(2026, 5, 7, 20, 0, tzinfo=UTC),  # idx 3 — Thu
    datetime(2026, 5, 8, 20, 0, tzinfo=UTC),  # idx 4 — Fri
    datetime(2026, 5, 11, 20, 0, tzinfo=UTC),  # idx 5 — Mon
    datetime(2026, 5, 12, 20, 0, tzinfo=UTC),  # idx 6 — Tue
    datetime(2026, 5, 13, 20, 0, tzinfo=UTC),  # idx 7 — Wed
    datetime(2026, 5, 14, 20, 0, tzinfo=UTC),  # idx 8 — Thu
    datetime(2026, 5, 15, 20, 0, tzinfo=UTC),  # idx 9 — Fri (last bar — no fwd1)
]
_MSFT_CLOSES = [100, 101, 103, 106, 104, 107, 108, 108, 109, 110]


@pytest.fixture
def msft_scoring_bars(db):
    """Ten consecutive MSFT trading-day bars used for forward-return scoring tests."""
    from apps.market.models import OHLCBar

    rows = [
        OHLCBar(
            ticker="MSFT",
            timeframe="1d",
            ts=ts,
            open=close - 0.5,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=2_000_000,
        )
        for ts, close in zip(_MSFT_TRADING_DAYS, _MSFT_CLOSES, strict=True)
    ]
    OHLCBar.objects.bulk_create(rows)


# ── Commit 1: forward-return scoring ────────────────────────────────────────


def test_matched_bars_carry_forward_return_fields(db, msft_scoring_bars) -> None:
    """Each matched BacktestMatch exposes fwd_1d_pct and fwd_5d_pct."""
    from apps.observer.triggers.backtest import BacktestMatch, backtest

    condition = {"all": [{"metric": "price", "ticker": "MSFT", "op": ">", "value": 102}]}
    matches = backtest(
        condition,
        start=_MSFT_TRADING_DAYS[0],
        end=_MSFT_TRADING_DAYS[-1],
    )
    # 8 matches (days 2-9, closes 103..110 all >102)
    assert len(matches) == 8
    for m in matches:
        assert isinstance(m, BacktestMatch)
        assert hasattr(m, "fwd_1d_pct")
        assert hasattr(m, "fwd_5d_pct")


def test_fwd_return_values_are_correct(db, msft_scoring_bars) -> None:
    """Hand-verify specific forward-return values for the first three matches."""
    from apps.observer.triggers.backtest import backtest

    condition = {"all": [{"metric": "price", "ticker": "MSFT", "op": ">", "value": 102}]}
    matches = backtest(
        condition,
        start=_MSFT_TRADING_DAYS[0],
        end=_MSFT_TRADING_DAYS[-1],
    )
    # day2 match (May6, close=103): fwd1=(106-103)/103*100=2.9126%, fwd5=(108-103)/103*100=4.8544%
    m0 = matches[0]
    assert m0.fwd_1d_pct is not None
    assert abs(m0.fwd_1d_pct - 2.9126) < 0.01
    assert m0.fwd_5d_pct is not None
    assert abs(m0.fwd_5d_pct - 4.8544) < 0.01

    # day3 match (May7, close=106): fwd1=(104-106)/106*100=-1.8868% (negative)
    m1 = matches[1]
    assert m1.fwd_1d_pct is not None
    assert abs(m1.fwd_1d_pct - (-1.8868)) < 0.01

    # day4 match (May8, close=104): fwd5=(110-104)/104*100=5.7692%
    m2 = matches[2]
    assert m2.fwd_5d_pct is not None
    assert abs(m2.fwd_5d_pct - 5.7692) < 0.01


def test_no_forward_bar_gives_none_score(db, msft_scoring_bars) -> None:
    """Coverage-honest: a match at the last bar has no forward data → None (not 0, not stale)."""
    from apps.observer.triggers.backtest import backtest

    condition = {"all": [{"metric": "price", "ticker": "MSFT", "op": ">", "value": 102}]}
    matches = backtest(
        condition,
        start=_MSFT_TRADING_DAYS[0],
        end=_MSFT_TRADING_DAYS[-1],
    )
    # day9 (May15, idx=7 in matches) is the last match — no fwd1 or fwd5 bar seeded
    last = matches[-1]
    assert last.ts == _MSFT_TRADING_DAYS[9]
    assert last.fwd_1d_pct is None, "last bar has no next trading-day bar — must be None, not 0"
    assert last.fwd_5d_pct is None

    # day5 (May11, idx=3 in matches): fwd1 exists, fwd5→May18 (no bar) → None
    m_day5 = matches[3]  # 4th match (days 2,3,4,5 → indices 0,1,2,3)
    assert m_day5.ts == _MSFT_TRADING_DAYS[5]
    assert m_day5.fwd_1d_pct is not None  # May12 bar exists
    assert m_day5.fwd_5d_pct is None  # May18 not seeded


def test_backtest_summary_counts_and_rates(db, msft_scoring_bars) -> None:
    """backtest_summary produces correct match/scored/avg/hit_rate stats from hand-built bars."""
    from apps.observer.triggers.backtest import backtest, backtest_summary

    condition = {"all": [{"metric": "price", "ticker": "MSFT", "op": ">", "value": 102}]}
    matches = backtest(
        condition,
        start=_MSFT_TRADING_DAYS[0],
        end=_MSFT_TRADING_DAYS[-1],
    )
    summary = backtest_summary(matches)

    # 8 matches total (price>102 at closes 103,106,104,107,108,108,109,110)
    assert summary["matches"] == 8

    # scored_1d = 7 (all except day9 which has no May18 bar)
    assert summary["scored_1d"] == 7

    # scored_5d = 3 (only days 2,3,4 have bars at +5 sessions: May13,14,15)
    assert summary["scored_5d"] == 3

    # avg_fwd_1d_pct: mean of [+2.9126,-1.8868,+2.8846,+0.9346, 0.0,+0.9259,+0.9174] ≈ 0.9555
    assert summary["avg_fwd_1d_pct"] is not None
    assert abs(summary["avg_fwd_1d_pct"] - 0.9555) < 0.01

    # hit_rate_1d: 5 of 7 positive (day2,day4,day5,day7,day8) → 5/7 ≈ 0.7143
    assert summary["hit_rate_1d"] == 0.7143

    # avg_fwd_5d_pct: mean of [+4.8544,+2.8302,+5.7692] ≈ 4.4846
    assert summary["avg_fwd_5d_pct"] is not None
    assert abs(summary["avg_fwd_5d_pct"] - 4.4846) < 0.01

    # hit_rate_5d: 3 of 3 positive → 1.0
    assert summary["hit_rate_5d"] == 1.0


def test_backtest_summary_no_matches() -> None:
    """backtest_summary on an empty list returns zeros and None rates."""
    from apps.observer.triggers.backtest import backtest_summary

    summary = backtest_summary([])
    assert summary["matches"] == 0
    assert summary["scored_1d"] == 0
    assert summary["avg_fwd_1d_pct"] is None
    assert summary["hit_rate_1d"] is None
    assert summary["scored_5d"] == 0
    assert summary["avg_fwd_5d_pct"] is None
    assert summary["hit_rate_5d"] is None


# ── Commit 2: vix leaf ───────────────────────────────────────────────────────


@pytest.fixture
def msft_and_vix_bars(db):
    """MSFT bars (same 10 days) + $VIX bars: VIX=18 on May4-6, VIX=22 on May7-15."""
    from apps.market.models import OHLCBar

    msft_rows = [
        OHLCBar(
            ticker="MSFT",
            timeframe="1d",
            ts=ts,
            open=close - 0.5,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=2_000_000,
        )
        for ts, close in zip(_MSFT_TRADING_DAYS, _MSFT_CLOSES, strict=True)
    ]
    # $VIX: low (18) on May4,5,6 → vix leaf fails even when price matches
    #       high (22) on May7-15 → vix leaf passes (>20)
    vix_values = [18, 18, 18, 22, 22, 22, 22, 22, 22, 22]
    vix_rows = [
        OHLCBar(
            ticker="$VIX",
            timeframe="1d",
            ts=ts,
            open=v - 0.5,
            high=v + 1,
            low=v - 1,
            close=v,
            volume=0,
        )
        for ts, v in zip(_MSFT_TRADING_DAYS, vix_values, strict=True)
    ]
    OHLCBar.objects.bulk_create(msft_rows + vix_rows)


def test_vix_leaf_gates_matches(db, msft_and_vix_bars) -> None:
    """With vix>20 AND price>102: May6 (price matches but VIX=18) must NOT match."""
    from apps.observer.triggers.backtest import backtest

    condition = {
        "all": [
            {"metric": "price", "ticker": "MSFT", "op": ">", "value": 102},
            {"metric": "vix", "op": ">", "value": 20},
        ]
    }
    matches = backtest(
        condition,
        start=_MSFT_TRADING_DAYS[0],
        end=_MSFT_TRADING_DAYS[-1],
    )
    # price>102 would match days 2-9 (8 bars), but VIX<20 on day2 (May6) blocks it.
    # VIX>=22>20 from day3 (May7) onwards → 7 matches
    assert len(matches) == 7

    # First match must be May7 (day3), not May6
    assert matches[0].ts == _MSFT_TRADING_DAYS[3]


def test_vix_absent_means_no_match(db, msft_scoring_bars) -> None:
    """Coverage-honest: no $VIX bars seeded → vix key absent → vix leaf never matches."""
    from apps.observer.triggers.backtest import backtest

    condition = {
        "all": [
            {"metric": "price", "ticker": "MSFT", "op": ">", "value": 102},
            {"metric": "vix", "op": ">", "value": 20},
        ]
    }
    # msft_scoring_bars has NO $VIX rows → vix always absent → no bar can satisfy both leaves
    matches = backtest(
        condition,
        start=_MSFT_TRADING_DAYS[0],
        end=_MSFT_TRADING_DAYS[-1],
    )
    assert matches == [], "no $VIX bars → vix leaf absent for every bar → zero matches"


def test_vix_only_condition_no_match_without_bars(db, msft_scoring_bars) -> None:
    """A pure vix condition returns no matches when $VIX bars are absent."""
    from apps.observer.triggers.backtest import backtest

    # Pure vix condition — _unique_tickers returns empty (vix has no ticker field),
    # so backtest returns [] immediately regardless of $VIX bar availability.
    condition = {"all": [{"metric": "vix", "op": ">", "value": 10}]}
    matches = backtest(
        condition,
        start=_MSFT_TRADING_DAYS[0],
        end=_MSFT_TRADING_DAYS[-1],
    )
    assert matches == []


# ── Commit 3: API response includes summary ──────────────────────────────────


def test_backtest_api_response_includes_summary(db, msft_scoring_bars) -> None:
    """The backtest endpoint now returns a 'summary' dict with all expected keys."""
    client = APIClient()
    resp = client.post(
        "/api/triggers/backtest/",
        data={
            "condition": {"all": [{"metric": "price", "ticker": "MSFT", "op": ">", "value": 102}]},
            # Use 2026-05-16 as end so all 10 bars (last at 2026-05-15 20:00 UTC) are in range.
            # ISO date strings parse to midnight; a same-day end would exclude the 20:00 bar.
            "start": "2026-05-04",
            "end": "2026-05-16",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()

    # summary key is present and has all expected sub-keys
    assert "summary" in body
    summary = body["summary"]
    for key in (
        "matches",
        "scored_1d",
        "avg_fwd_1d_pct",
        "hit_rate_1d",
        "scored_5d",
        "avg_fwd_5d_pct",
        "hit_rate_5d",
    ):
        assert key in summary, f"summary missing key {key!r}"

    # Numeric sanity: 8 matches, hit_rate values are in [0,1] or None
    assert summary["matches"] == 8
    if summary["hit_rate_1d"] is not None:
        assert 0.0 <= summary["hit_rate_1d"] <= 1.0
    if summary["hit_rate_5d"] is not None:
        assert 0.0 <= summary["hit_rate_5d"] <= 1.0

    # per-match dicts now carry fwd_1d_pct and fwd_5d_pct keys
    for m in body["matches"]:
        assert "fwd_1d_pct" in m
        assert "fwd_5d_pct" in m

    # existing keys still present (additive, not breaking)
    assert "match_count" in body
    assert "matches" in body


def test_backtest_api_summary_values(db, msft_scoring_bars) -> None:
    """The API summary carries the same numeric values as backtest_summary()."""
    client = APIClient()
    resp = client.post(
        "/api/triggers/backtest/",
        data={
            "condition": {"all": [{"metric": "price", "ticker": "MSFT", "op": ">", "value": 102}]},
            "start": "2026-05-04",
            "end": "2026-05-16",  # past last bar (20:00 UTC on May15) so all 10 bars included
        },
        format="json",
    )
    assert resp.status_code == 200
    summary = resp.json()["summary"]

    # 8 matches (closes 103..110 all >102), scored_1d=7 (day9/May15 has no fwd1 bar)
    assert summary["scored_1d"] == 7
    assert summary["scored_5d"] == 3
    assert summary["hit_rate_1d"] == 0.7143  # 5/7, rounded to 4 dp
    assert summary["hit_rate_5d"] == 1.0  # 3/3
    assert abs(summary["avg_fwd_1d_pct"] - 0.9555) < 0.01
    assert abs(summary["avg_fwd_5d_pct"] - 4.4846) < 0.01
