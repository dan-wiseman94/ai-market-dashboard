"""Corporate-action adjustment in the returns math (C3).

The headline bug: a stock split divides the price, so an unadjusted forward
return reads a 3:1 split as a -66% crash. These tests pin the corrected behaviour
and prove the common no-split path is unchanged.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from django.test import override_settings

from apps.market.models import CorporateAction, OHLCBar
from apps.market.returns import (
    forward_return_pct,
    price_path_summary,
    split_factor,
)

START = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
END = datetime(2026, 3, 6, 15, 0, tzinfo=UTC)  # ~60 days later


def _mk_bar(ticker: str, ts: datetime, close: float, *, high=None, low=None) -> None:
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1h",
        ts=ts,
        open=close,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=1,
    )


def _split(ticker: str, ex_date: date, ratio: float) -> None:
    CorporateAction.objects.create(
        source="test",
        external_id=f"SPLIT:{ticker}:{ex_date}",
        kind="split",
        ticker=ticker,
        ex_date=ex_date,
        ratio=ratio,
    )


def _div(ticker: str, ex_date: date, amount: float) -> None:
    CorporateAction.objects.create(
        source="test",
        external_id=f"DIV:{ticker}:{ex_date}",
        kind="dividend",
        ticker=ticker,
        ex_date=ex_date,
        amount=amount,
    )


class TestSplitAdjustment:
    def test_forward_split_no_longer_reads_as_crash(self, db) -> None:
        # Entry $300; a 3:1 split mid-window divides price to $100 (economically flat).
        _mk_bar("NVDA", START, 300.0)
        _mk_bar("NVDA", END, 100.0)
        _split("NVDA", date(2026, 2, 1), 3.0)
        # Naive (100-300)/300 = -66.7%; adjusted 100*3 == 300 -> ~0%.
        assert forward_return_pct("NVDA", START, END) == pytest.approx(0.0)

    def test_no_split_leaves_return_unchanged(self, db) -> None:
        _mk_bar("AAPL", START, 100.0)
        _mk_bar("AAPL", END, 110.0)
        assert forward_return_pct("AAPL", START, END) == pytest.approx(10.0)

    def test_reverse_split_adjusts(self, db) -> None:
        # 1:10 reverse split (ratio 0.1): $5 -> $50, economically flat.
        _mk_bar("RVRS", START, 5.0)
        _mk_bar("RVRS", END, 50.0)
        _split("RVRS", date(2026, 2, 1), 0.1)
        assert forward_return_pct("RVRS", START, END) == pytest.approx(0.0)

    def test_real_gain_through_a_split_is_preserved(self, db) -> None:
        # Entry $300, 3:1 split, then a genuine +10%: post-split $110 == $330 pre-basis.
        _mk_bar("NVDA", START, 300.0)
        _mk_bar("NVDA", END, 110.0)
        _split("NVDA", date(2026, 2, 1), 3.0)
        assert forward_return_pct("NVDA", START, END) == pytest.approx(10.0)

    def test_split_on_start_date_is_excluded(self, db) -> None:
        # ex_date == start.date(): the start close is already post-split -> NOT adjusted.
        _mk_bar("NVDA", START, 100.0)
        _mk_bar("NVDA", END, 110.0)
        _split("NVDA", START.date(), 3.0)
        assert forward_return_pct("NVDA", START, END) == pytest.approx(10.0)

    def test_split_on_end_date_is_included(self, db) -> None:
        _mk_bar("NVDA", START, 300.0)
        _mk_bar("NVDA", END, 100.0)
        _split("NVDA", END.date(), 3.0)
        assert forward_return_pct("NVDA", START, END) == pytest.approx(0.0)


class TestSplitFactor:
    def test_no_actions_is_one(self, db) -> None:
        assert split_factor("AAPL", START, END) == 1.0

    def test_multiple_splits_multiply(self, db) -> None:
        _split("X", date(2026, 1, 20), 2.0)
        _split("X", date(2026, 2, 20), 3.0)
        assert split_factor("X", START, END) == pytest.approx(6.0)

    def test_only_splits_strictly_in_window_count(self, db) -> None:
        _split("X", date(2025, 12, 1), 2.0)  # before start
        _split("X", date(2026, 2, 1), 3.0)  # inside
        _split("X", date(2026, 6, 1), 5.0)  # after end
        assert split_factor("X", START, END) == pytest.approx(3.0)


class TestPricePathSummary:
    def test_exposes_split_factor_and_keeps_prices_raw(self, db) -> None:
        _mk_bar("NVDA", START, 300.0, high=310.0, low=295.0)
        _mk_bar("NVDA", END, 100.0, high=105.0, low=99.0)
        _split("NVDA", date(2026, 2, 1), 3.0)
        out = price_path_summary("NVDA", START, END)
        assert out["start_close"] == pytest.approx(300.0)  # raw observed
        assert out["end_close"] == pytest.approx(100.0)  # raw observed
        assert out["max_high"] == pytest.approx(310.0)  # raw observed extreme
        assert out["return_pct"] == pytest.approx(0.0)  # split-adjusted
        assert out["split_factor"] == pytest.approx(3.0)
        assert out["adjusted"] is True

    def test_no_split_reports_factor_one_not_adjusted(self, db) -> None:
        _mk_bar("AAPL", START, 100.0)
        _mk_bar("AAPL", END, 120.0)
        out = price_path_summary("AAPL", START, END)
        assert out["split_factor"] == 1.0
        assert out["adjusted"] is False
        assert out["return_pct"] == pytest.approx(20.0)


class TestDividendOptIn:
    def test_dividends_ignored_by_default(self, db) -> None:
        # Default is price-return: a dividend in the window does NOT lift the number.
        _mk_bar("AAPL", START, 100.0)
        _mk_bar("AAPL", END, 100.0)
        _div("AAPL", date(2026, 2, 1), 5.0)
        assert forward_return_pct("AAPL", START, END) == pytest.approx(0.0)

    @override_settings(RETURNS_ADJUST_DIVIDENDS=True)
    def test_dividends_add_to_total_return_when_enabled(self, db) -> None:
        _mk_bar("AAPL", START, 100.0)
        _mk_bar("AAPL", END, 100.0)
        _div("AAPL", date(2026, 2, 1), 5.0)
        # total return = (100 + 5 - 100) / 100 = 5%
        assert forward_return_pct("AAPL", START, END) == pytest.approx(5.0)

    @override_settings(RETURNS_ADJUST_DIVIDENDS=True)
    def test_dividend_after_split_scaled_onto_start_basis(self, db) -> None:
        # $300 entry; 3:1 split to $100 (flat); a $3/share dividend AFTER the split.
        # Post-split the holder has 3 shares: 3 * $3 = $9 on the start-share basis.
        # total = (100*3 + 9 - 300) / 300 = 3%.
        _mk_bar("NVDA", START, 300.0)
        _mk_bar("NVDA", END, 100.0)
        _split("NVDA", date(2026, 2, 1), 3.0)
        _div("NVDA", date(2026, 2, 15), 3.0)
        assert forward_return_pct("NVDA", START, END) == pytest.approx(3.0)
