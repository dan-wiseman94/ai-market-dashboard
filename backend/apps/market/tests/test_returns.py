"""Tests for apps.market.returns — forward-return helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.market.returns import (
    forward_return_pct,
    nearest_bar_close,
    price_path_summary,
)


def _aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


BASE = datetime(2026, 4, 10, 14, 0)


class TestNearestBarClose:
    def test_returns_close_for_exact_timestamp(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE, 150.0)
        result = nearest_bar_close("AAPL", _aware(BASE))
        assert result == pytest.approx(150.0)

    def test_returns_most_recent_bar_within_1h_window(self, db, mk_bar) -> None:
        # bar at BASE, querying at BASE + 30min — should still find it (ts__lte at+1h)
        mk_bar("AAPL", BASE, 150.0)
        result = nearest_bar_close("AAPL", _aware(BASE + timedelta(minutes=30)))
        assert result == pytest.approx(150.0)

    def test_prefers_most_recent_bar_when_multiple_exist(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE - timedelta(hours=2), 140.0)
        mk_bar("AAPL", BASE, 150.0)
        result = nearest_bar_close("AAPL", _aware(BASE))
        assert result == pytest.approx(150.0)

    def test_returns_none_when_no_bars_for_ticker(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE, 150.0)
        result = nearest_bar_close("ZZZZ", _aware(BASE))
        assert result is None

    def test_returns_none_when_no_bars_at_all(self, db) -> None:
        result = nearest_bar_close("AAPL", _aware(BASE))
        assert result is None

    def test_does_not_return_bar_more_than_1h_beyond_at(self, db, mk_bar) -> None:
        # bar is 2h in the future relative to `at` — outside the lte window
        mk_bar("AAPL", BASE + timedelta(hours=2), 200.0)
        result = nearest_bar_close("AAPL", _aware(BASE))
        assert result is None


@pytest.mark.parametrize(
    "start_close, end_close, expected",
    [
        (100.0, 110.0, 10.0),
        (100.0, 90.0, -10.0),
        (100.0, 100.0, 0.0),
    ],
)
def test_forward_return_pct_parametrized(db, mk_bar, start_close, end_close, expected) -> None:
    start = _aware(BASE)
    end = _aware(BASE + timedelta(hours=24))
    mk_bar("AAPL", BASE, start_close)
    mk_bar("AAPL", BASE + timedelta(hours=24), end_close)
    result = forward_return_pct("AAPL", start, end)
    assert result == pytest.approx(expected, rel=0.01)


def test_forward_return_pct_none_when_no_start_bar(db, mk_bar) -> None:
    start = _aware(BASE)
    end = _aware(BASE + timedelta(hours=24))
    mk_bar("AAPL", BASE + timedelta(hours=24), 110.0)
    result = forward_return_pct("AAPL", start, end)
    assert result is None


def test_forward_return_pct_none_when_t0_has_no_bar(db, mk_bar) -> None:
    # ZEND has no bar at or before start+1h, so nearest_bar_close returns None
    # for t0, which causes forward_return_pct to return None.
    # The only ZEND bar is 2h past `end` — outside both the start and end windows.
    start = _aware(BASE)
    end = _aware(BASE + timedelta(hours=24))
    mk_bar("AAPL", BASE, 100.0)  # unrelated ticker; ZEND has no bar at start
    mk_bar("ZEND", BASE + timedelta(hours=26), 200.0)  # 2h after end+1h boundary
    result = forward_return_pct("ZEND", start, end)
    assert result is None


def test_forward_return_pct_none_when_start_close_is_zero(db, mk_bar) -> None:
    start = _aware(BASE)
    end = _aware(BASE + timedelta(hours=24))
    mk_bar("AAPL", BASE, 0.0)
    mk_bar("AAPL", BASE + timedelta(hours=24), 10.0)
    result = forward_return_pct("AAPL", start, end)
    assert result is None


def test_forward_return_pct_none_for_unknown_ticker(db, mk_bar) -> None:
    start = _aware(BASE)
    end = _aware(BASE + timedelta(hours=24))
    mk_bar("AAPL", BASE, 100.0)
    mk_bar("AAPL", BASE + timedelta(hours=24), 110.0)
    result = forward_return_pct("ZZZZ", start, end)
    assert result is None


class TestPricePathSummary:
    def test_empty_range_returns_nones_and_zero_bars(self, db) -> None:
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=5))
        result = price_path_summary("AAPL", start, end)
        assert result["start_close"] is None
        assert result["end_close"] is None
        assert result["return_pct"] is None
        assert result["max_high"] is None
        assert result["min_low"] is None
        assert result["bars"] == 0

    def test_single_bar_in_range(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE + timedelta(hours=1), 100.0, high=105.0, low=95.0)
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=2))
        result = price_path_summary("AAPL", start, end)
        assert result["bars"] == 1
        assert result["max_high"] == pytest.approx(105.0)
        assert result["min_low"] == pytest.approx(95.0)

    def test_max_high_and_min_low_across_multiple_bars(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE + timedelta(hours=1), 100.0, high=110.0, low=90.0)
        mk_bar("AAPL", BASE + timedelta(hours=2), 102.0, high=120.0, low=85.0)
        mk_bar("AAPL", BASE + timedelta(hours=3), 105.0, high=115.0, low=92.0)
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=4))
        result = price_path_summary("AAPL", start, end)
        assert result["bars"] == 3
        assert result["max_high"] == pytest.approx(120.0)
        assert result["min_low"] == pytest.approx(85.0)

    def test_start_close_and_end_close_correct(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE, 100.0)
        mk_bar("AAPL", BASE + timedelta(hours=24), 115.0)
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=24))
        result = price_path_summary("AAPL", start, end)
        assert result["start_close"] == pytest.approx(100.0)
        assert result["end_close"] == pytest.approx(115.0)

    def test_return_pct_matches_forward_return_pct(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE, 100.0)
        mk_bar("AAPL", BASE + timedelta(hours=24), 115.0)
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=24))
        result = price_path_summary("AAPL", start, end)
        expected = forward_return_pct("AAPL", start, end)
        assert result["return_pct"] == pytest.approx(expected, rel=0.01)

    def test_bars_count_includes_only_range(self, db, mk_bar) -> None:
        # bars at BASE-1h (outside), BASE+1h (inside), BASE+2h (inside), BASE+25h (outside)
        mk_bar("AAPL", BASE - timedelta(hours=1), 99.0)
        mk_bar("AAPL", BASE + timedelta(hours=1), 100.0)
        mk_bar("AAPL", BASE + timedelta(hours=2), 101.0)
        mk_bar("AAPL", BASE + timedelta(hours=25), 110.0)
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=24))
        result = price_path_summary("AAPL", start, end)
        assert result["bars"] == 2

    def test_max_high_min_low_are_floats_not_decimal(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE + timedelta(hours=1), 100.0, high=110.0, low=90.0)
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=2))
        result = price_path_summary("AAPL", start, end)
        assert isinstance(result["max_high"], float)
        assert isinstance(result["min_low"], float)

    def test_unknown_ticker_returns_empty(self, db, mk_bar) -> None:
        mk_bar("AAPL", BASE + timedelta(hours=1), 100.0)
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=2))
        result = price_path_summary("ZZZZ", start, end)
        assert result["bars"] == 0
        assert result["max_high"] is None
        assert result["min_low"] is None
        assert result["return_pct"] is None

    def test_bar_in_grace_window_affects_end_close_not_bars_or_highs(self, db, mk_bar) -> None:
        # A bar that falls in (end, end+1h] is picked up by nearest_bar_close's
        # ts__lte=end+1h filter, so it influences end_close.  But the aggregate
        # query uses ts__lte=end (strict), so that same bar must NOT be counted
        # in bars and must NOT affect max_high or min_low.
        start = _aware(BASE)
        end = _aware(BASE + timedelta(hours=5))

        mk_bar("AAPL", BASE, 100.0, high=100.0, low=100.0)  # at start, inside range
        grace_bar_ts = BASE + timedelta(hours=5, minutes=30)  # inside (end, end+1h]
        mk_bar("AAPL", grace_bar_ts, 200.0, high=250.0, low=50.0)  # outside strict range

        result = price_path_summary("AAPL", start, end)

        # end_close comes from nearest_bar_close which uses ts__lte=end+1h
        assert result["end_close"] == pytest.approx(200.0)

        # The grace-window bar must NOT be counted in bars or extremes
        assert result["bars"] == 1  # only the start bar at BASE
        assert result["max_high"] == pytest.approx(100.0)  # grace bar's high=250 excluded
        assert result["min_low"] == pytest.approx(100.0)  # grace bar's low=50 excluded
