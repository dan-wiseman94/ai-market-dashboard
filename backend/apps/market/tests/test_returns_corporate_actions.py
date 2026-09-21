"""Corporate-action adjustment in the returns math.

The headline failure mode: a stock split divides the price, so an unadjusted
forward return reads a 3:1 split as a -66% crash. These tests pin the
split-adjusted behaviour and prove the common no-split path is unaffected.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from django.test import override_settings

from apps.market.models import CorporateAction
from apps.market.returns import (
    _corporate_actions,
    _split_product,
    forward_return_pct,
    price_path_summary,
)

START = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
END = datetime(2026, 3, 6, 15, 0, tzinfo=UTC)  # ~60 days later


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
    def test_forward_split_no_longer_reads_as_crash(self, db, mk_bar) -> None:
        # Entry $300; a 3:1 split mid-window divides price to $100 (economically flat).
        mk_bar("NVDA", START, 300.0)
        mk_bar("NVDA", END, 100.0)
        _split("NVDA", date(2026, 2, 1), 3.0)
        # Naive (100-300)/300 = -66.7%; adjusted 100*3 == 300 -> ~0%.
        assert forward_return_pct("NVDA", START, END) == pytest.approx(0.0)

    def test_no_split_leaves_return_unchanged(self, db, mk_bar) -> None:
        mk_bar("AAPL", START, 100.0)
        mk_bar("AAPL", END, 110.0)
        assert forward_return_pct("AAPL", START, END) == pytest.approx(10.0)

    def test_reverse_split_adjusts(self, db, mk_bar) -> None:
        # 1:10 reverse split (ratio 0.1): $5 -> $50, economically flat.
        mk_bar("RVRS", START, 5.0)
        mk_bar("RVRS", END, 50.0)
        _split("RVRS", date(2026, 2, 1), 0.1)
        assert forward_return_pct("RVRS", START, END) == pytest.approx(0.0)

    def test_real_gain_through_a_split_is_preserved(self, db, mk_bar) -> None:
        # Entry $300, 3:1 split, then a genuine +10%: post-split $110 == $330 pre-basis.
        mk_bar("NVDA", START, 300.0)
        mk_bar("NVDA", END, 110.0)
        _split("NVDA", date(2026, 2, 1), 3.0)
        assert forward_return_pct("NVDA", START, END) == pytest.approx(10.0)

    def test_split_on_start_date_is_excluded(self, db, mk_bar) -> None:
        # ex_date == start.date(): the start close is already post-split -> NOT adjusted.
        mk_bar("NVDA", START, 100.0)
        mk_bar("NVDA", END, 110.0)
        _split("NVDA", START.date(), 3.0)
        assert forward_return_pct("NVDA", START, END) == pytest.approx(10.0)

    def test_split_on_end_date_is_included(self, db, mk_bar) -> None:
        mk_bar("NVDA", START, 300.0)
        mk_bar("NVDA", END, 100.0)
        _split("NVDA", END.date(), 3.0)
        assert forward_return_pct("NVDA", START, END) == pytest.approx(0.0)


def _window_split_factor(ticker: str) -> float:
    """Π split ratios for ex-dates in ``(START, END]`` — the exact composition
    :func:`_adjusted_end_value` uses to restore an end close to the start basis."""
    return _split_product(_corporate_actions(ticker, START, END))


class TestSplitFactor:
    def test_no_actions_is_one(self, db) -> None:
        assert _window_split_factor("AAPL") == 1.0

    def test_multiple_splits_multiply(self, db) -> None:
        _split("X", date(2026, 1, 20), 2.0)
        _split("X", date(2026, 2, 20), 3.0)
        assert _window_split_factor("X") == pytest.approx(6.0)

    def test_only_splits_strictly_in_window_count(self, db) -> None:
        _split("X", date(2025, 12, 1), 2.0)  # before start
        _split("X", date(2026, 2, 1), 3.0)  # inside
        _split("X", date(2026, 6, 1), 5.0)  # after end
        assert _window_split_factor("X") == pytest.approx(3.0)


class TestPricePathSummary:
    def test_exposes_split_factor_and_keeps_prices_raw(self, db, mk_bar) -> None:
        mk_bar("NVDA", START, 300.0, high=310.0, low=295.0)
        mk_bar("NVDA", END, 100.0, high=105.0, low=99.0)
        _split("NVDA", date(2026, 2, 1), 3.0)
        out = price_path_summary("NVDA", START, END)
        assert out["start_close"] == pytest.approx(300.0)  # raw observed
        assert out["end_close"] == pytest.approx(100.0)  # raw observed
        assert out["max_high"] == pytest.approx(310.0)  # raw observed extreme
        assert out["return_pct"] == pytest.approx(0.0)  # split-adjusted
        assert out["split_factor"] == pytest.approx(3.0)
        assert out["adjusted"] is True

    def test_no_split_reports_factor_one_not_adjusted(self, db, mk_bar) -> None:
        mk_bar("AAPL", START, 100.0)
        mk_bar("AAPL", END, 120.0)
        out = price_path_summary("AAPL", START, END)
        assert out["split_factor"] == 1.0
        assert out["adjusted"] is False
        assert out["return_pct"] == pytest.approx(20.0)


class TestDividendOptIn:
    def test_dividends_ignored_by_default(self, db, mk_bar) -> None:
        # Default is price-return: a dividend in the window does NOT lift the number.
        mk_bar("AAPL", START, 100.0)
        mk_bar("AAPL", END, 100.0)
        _div("AAPL", date(2026, 2, 1), 5.0)
        assert forward_return_pct("AAPL", START, END) == pytest.approx(0.0)

    @override_settings(RETURNS_ADJUST_DIVIDENDS=True)
    def test_dividends_add_to_total_return_when_enabled(self, db, mk_bar) -> None:
        mk_bar("AAPL", START, 100.0)
        mk_bar("AAPL", END, 100.0)
        _div("AAPL", date(2026, 2, 1), 5.0)
        # total return = (100 + 5 - 100) / 100 = 5%
        assert forward_return_pct("AAPL", START, END) == pytest.approx(5.0)

    @override_settings(RETURNS_ADJUST_DIVIDENDS=True)
    def test_dividend_after_split_scaled_onto_start_basis(self, db, mk_bar) -> None:
        # $300 entry; 3:1 split to $100 (flat); a $3/share dividend AFTER the split.
        # Post-split the holder has 3 shares: 3 * $3 = $9 on the start-share basis.
        # total = (100*3 + 9 - 300) / 300 = 3%.
        mk_bar("NVDA", START, 300.0)
        mk_bar("NVDA", END, 100.0)
        _split("NVDA", date(2026, 2, 1), 3.0)
        _div("NVDA", date(2026, 2, 15), 3.0)
        assert forward_return_pct("NVDA", START, END) == pytest.approx(3.0)


def _knob_queries(ctx) -> int:
    """Queries in *ctx* that touch the SystemSettings singleton."""
    return sum("core_systemsettings" in q["sql"] for q in ctx.captured_queries)


class TestDividendKnobWiring:
    """The UI switch (SystemSettings.returns_adjust_dividends) must actually reach
    the math, and resolving it must not cost a row fetch per loop item."""

    def test_system_settings_override_reaches_the_math(self, db, mk_bar) -> None:
        from apps.core.models import SystemSettings

        mk_bar("AAPL", START, 100.0)
        mk_bar("AAPL", END, 100.0)
        _div("AAPL", date(2026, 2, 1), 5.0)
        assert forward_return_pct("AAPL", START, END) == pytest.approx(0.0)

        cfg = SystemSettings.load()
        cfg.returns_adjust_dividends = True
        cfg.save(update_fields=["returns_adjust_dividends"])
        assert forward_return_pct("AAPL", START, END) == pytest.approx(5.0)

    def test_explicit_argument_beats_the_stored_knob(self, db, mk_bar) -> None:
        from apps.core.models import SystemSettings

        mk_bar("AAPL", START, 100.0)
        mk_bar("AAPL", END, 100.0)
        _div("AAPL", date(2026, 2, 1), 5.0)
        cfg = SystemSettings.load()
        cfg.returns_adjust_dividends = True
        cfg.save(update_fields=["returns_adjust_dividends"])
        assert forward_return_pct("AAPL", START, END, adjust_dividends=False) == pytest.approx(0.0)

    def test_batch_resolves_the_knob_once_for_the_whole_batch(self, db, mk_bar) -> None:
        """Query count is flat in the number of requests — the knob is resolved for
        the batch, not per item (the leaderboard pins a max-query budget over this)."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from apps.core.models import SystemSettings
        from apps.market.returns import trading_day_forward_returns

        for t in ("AAPL", "MSFT", "NVDA"):
            mk_bar(t, START, 100.0)
            mk_bar(t, END, 100.0)
            _div(t, date(2026, 2, 1), 5.0)

        SystemSettings.load()  # created up front so only the read is measured

        with CaptureQueriesContext(connection) as ctx:
            trading_day_forward_returns([("AAPL", START), ("MSFT", START), ("NVDA", START)], 24)
        assert _knob_queries(ctx) == 1

    def test_dividend_free_window_never_reads_the_knob(self, db, mk_bar) -> None:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        mk_bar("AAPL", START, 100.0)
        mk_bar("AAPL", END, 120.0)
        with CaptureQueriesContext(connection) as ctx:
            forward_return_pct("AAPL", START, END)
        # No dividend in the window: the knob cannot change the answer, so it is
        # never fetched.
        assert _knob_queries(ctx) == 0
