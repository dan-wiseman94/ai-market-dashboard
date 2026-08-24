"""VX contract symbology + settlement dates + front/second selection."""

from __future__ import annotations

import datetime as dt
from unittest.mock import patch

import pytest

from apps.market.schwab_client import SchwabNotConnectedError
from apps.market.services.vix import (
    front_and_second,
    vix_term_structure,
    vx_contract_symbol,
    vx_settlement_date,
)

TODAY = dt.date(2026, 8, 24)  # front=/VXU26 (2026-09-16), second=/VXV26 (2026-10-21)


@pytest.mark.parametrize(
    ("month", "code"),
    [
        (1, "F"),
        (2, "G"),
        (3, "H"),
        (4, "J"),
        (5, "K"),
        (6, "M"),
        (7, "N"),
        (8, "Q"),
        (9, "U"),
        (10, "V"),
        (11, "X"),
        (12, "Z"),
    ],
)
def test_contract_symbol_month_codes(month, code):
    assert vx_contract_symbol(2026, month) == f"/VX{code}26"


def test_contract_symbol_two_digit_year():
    assert vx_contract_symbol(2031, 1) == "/VXF31"


@pytest.mark.parametrize(
    ("year", "month", "expected"),
    [
        # Wednesday 30 days before the third Friday of the following month.
        (2026, 1, dt.date(2026, 1, 21)),  # Feb 20 2026 - 30d
        (2026, 8, dt.date(2026, 8, 19)),  # Sep 18 2026 - 30d
        (2026, 9, dt.date(2026, 9, 16)),  # Oct 16 2026 - 30d
        (2026, 10, dt.date(2026, 10, 21)),  # Nov 20 2026 - 30d
        # Year rollover: the anchor Friday lives in January of the next year.
        (2026, 12, dt.date(2026, 12, 16)),  # Jan 15 2027 - 30d
    ],
)
def test_settlement_date_normal_months(year, month, expected):
    assert vx_settlement_date(year, month) == expected


def test_settlement_date_holiday_anchor_rolls_back():
    # April 17 2025's third Friday (Apr 18) was Good Friday, so the anchor is
    # the preceding business day and settlement lands on a TUESDAY.
    assert vx_settlement_date(2025, 3) == dt.date(2025, 3, 18)


@pytest.mark.parametrize(
    ("year", "month", "expected"),
    [
        # Juneteenth fell ON the nominal settlement Wednesday (Jun 19) — Cboe
        # moves settlement to the preceding business day. The June 2024
        # contract really settled Tuesday 2024-06-18.
        (2024, 6, dt.date(2024, 6, 18)),
        (2030, 6, dt.date(2030, 6, 18)),
    ],
)
def test_settlement_date_holiday_wednesday_rolls_back(year, month, expected):
    assert vx_settlement_date(year, month) == expected


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        # Mid-cycle: Aug contract settled Aug 19, so Sep/Oct are the pair.
        (
            dt.date(2026, 8, 24),
            [("/VXU26", dt.date(2026, 9, 16)), ("/VXV26", dt.date(2026, 10, 21))],
        ),
        # The day BEFORE settlement the expiring contract is still front.
        (
            dt.date(2026, 8, 18),
            [("/VXQ26", dt.date(2026, 8, 19)), ("/VXU26", dt.date(2026, 9, 16))],
        ),
        # ON settlement day the contract prices off the morning SOQ — roll.
        (
            dt.date(2026, 8, 19),
            [("/VXU26", dt.date(2026, 9, 16)), ("/VXV26", dt.date(2026, 10, 21))],
        ),
        # December: the pair spans a year boundary.
        (
            dt.date(2026, 12, 20),
            [("/VXF27", dt.date(2027, 1, 20)), ("/VXG27", dt.date(2027, 2, 17))],
        ),
    ],
)
def test_front_and_second_selection(today, expected):
    assert front_and_second(today) == expected


def _quotes(mapping):
    return patch("apps.market.services.vix.fetch_quotes", return_value=mapping)


def test_term_structure_full():
    with _quotes(
        {
            "$VIX": {"last": 15.2, "pct_change": -3.1},
            "/VX": {"last": 16.75, "pct_change": -1.9},
            "/VXU26": {"last": 16.8, "pct_change": -2.0},
            "/VXV26": {"last": 17.9, "pct_change": -1.1},
        }
    ) as mock:
        payload = vix_term_structure(today=TODAY)

    (symbols,) = mock.call_args.args
    assert symbols == ["$VIX", "/VX", "/VXU26", "/VXV26"]
    assert payload["spot"] == {"symbol": "$VIX", "last": 15.2, "pct_change": -3.1}
    assert payload["front"] == {
        "symbol": "/VXU26",
        "expiry": "2026-09-16",
        "continuous": False,
        "last": 16.8,
        "pct_change": -2.0,
        "basis": 1.6,
        "basis_pct": 10.53,
    }
    assert payload["second"] == {
        "symbol": "/VXV26",
        "expiry": "2026-10-21",
        "last": 17.9,
        "pct_change": -1.1,
    }
    assert payload["contango_pct"] == 6.55
    assert payload["structure"] == "contango"
    assert "note" not in payload


def test_term_structure_backwardation():
    with _quotes(
        {
            "$VIX": {"last": 28.0, "pct_change": 12.0},
            "/VXU26": {"last": 25.0, "pct_change": 8.0},
            "/VXV26": {"last": 23.5, "pct_change": 6.0},
        }
    ):
        payload = vix_term_structure(today=TODAY)
    assert payload["contango_pct"] == -6.0
    assert payload["structure"] == "backwardation"
    assert payload["front"]["basis"] == -3.0


def test_term_structure_dated_front_missing_falls_back_to_continuous():
    with _quotes(
        {
            "$VIX": {"last": 15.0, "pct_change": 0.5},
            "/VX": {"last": 16.5, "pct_change": 0.2},
            "/VXV26": {"last": 17.5, "pct_change": 0.1},
        }
    ):
        payload = vix_term_structure(today=TODAY)
    assert payload["front"]["symbol"] == "/VX"
    assert payload["front"]["continuous"] is True
    assert payload["front"]["expiry"] is None
    assert payload["front"]["basis"] == 1.5
    assert payload["structure"] == "contango"


def test_term_structure_no_futures_degrades_to_spot_with_note():
    with _quotes({"$VIX": {"last": 15.0, "pct_change": 0.5}}):
        payload = vix_term_structure(today=TODAY)
    assert payload["spot"]["last"] == 15.0
    assert payload["front"] is None
    assert payload["second"] is None
    assert payload["contango_pct"] is None
    assert payload["structure"] is None
    assert "Schwab" in payload["note"]


def test_term_structure_second_missing_notes_incomplete_structure():
    with _quotes(
        {
            "$VIX": {"last": 15.0, "pct_change": 0.5},
            "/VXU26": {"last": 16.0, "pct_change": 0.2},
        }
    ):
        payload = vix_term_structure(today=TODAY)
    assert payload["front"]["symbol"] == "/VXU26"
    assert payload["second"] is None
    assert payload["contango_pct"] is None
    assert "note" in payload


def test_term_structure_empty_quotes_raises():
    with _quotes({}), pytest.raises(RuntimeError):
        vix_term_structure(today=TODAY)


_NONE_ROW = {"last": None, "bid": None, "ask": None, "volume": None, "pct_change": None}


def test_term_structure_all_none_rows_raise():
    # Twelve Data answers unknown symbols with per-symbol error objects that
    # normalize to all-None rows — present keys, no data.
    with (
        _quotes({s: dict(_NONE_ROW) for s in ("$VIX", "/VX", "/VXU26", "/VXV26")}),
        pytest.raises(RuntimeError),
    ):
        vix_term_structure(today=TODAY)


def test_term_structure_none_futures_rows_degrade_to_spot_with_note():
    with _quotes(
        {
            "$VIX": {"last": 15.0, "pct_change": 0.5},
            "/VX": dict(_NONE_ROW),
            "/VXU26": dict(_NONE_ROW),
            "/VXV26": dict(_NONE_ROW),
        }
    ):
        payload = vix_term_structure(today=TODAY)
    assert payload["spot"]["last"] == 15.0
    assert payload["front"] is None
    assert payload["second"] is None
    assert "Schwab" in payload["note"]


def test_term_structure_zero_price_rows_are_unusable():
    # A 0.0 last is a feed placeholder, never a real VIX print — treating it
    # as data would fabricate a -100% basis.
    with (
        _quotes(
            {
                "$VIX": {"last": 0.0, "pct_change": None},
                "/VXU26": {"last": 0.0, "pct_change": None},
            }
        ),
        pytest.raises(RuntimeError),
    ):
        vix_term_structure(today=TODAY)


def test_term_structure_not_connected_propagates():
    with (
        patch(
            "apps.market.services.vix.fetch_quotes",
            side_effect=SchwabNotConnectedError("no token"),
        ),
        pytest.raises(SchwabNotConnectedError),
    ):
        vix_term_structure(today=TODAY)
