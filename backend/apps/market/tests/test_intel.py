from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from apps.market.models import OptionChainSnapshot
from apps.market.services.intel import iv_summary, sector_rotation


@patch("apps.market.services.intel.fetch_quotes")
def test_sector_rotation_ranks_desc_with_sector_names(mock_fq):
    mock_fq.return_value = {
        "XLK": {"last": 1, "pct_change": 1.8},
        "XLF": {"last": 1, "pct_change": 0.9},
        "XLE": {"last": 1, "pct_change": -1.2},
    }
    out = sector_rotation()
    assert [r["etf"] for r in out["ranked"]] == ["XLK", "XLF", "XLE"]
    assert out["ranked"][0] == {"etf": "XLK", "sector": "Technology", "pct": 1.8}
    assert out["ranked"][-1]["pct"] == -1.2


@patch("apps.market.services.intel.fetch_quotes")
def test_sector_rotation_drops_none_pct_and_empty_is_none(mock_fq):
    mock_fq.return_value = {"XLK": {"pct_change": None}, "XLF": {}}
    assert sector_rotation() is None


def _chain(ticker, *, when, expiries):
    """expiries: {exp: {"calls": [line...], "puts": [line...]}}; line = {"strike","iv",...}."""
    snap = OptionChainSnapshot.objects.create(
        ticker=ticker,
        expiries=list(expiries.keys()),
        payload={"underlying_last": "100.00", "expiries": expiries, "ticker": ticker},
    )
    OptionChainSnapshot.objects.filter(id=snap.id).update(fetched_at=when)
    return snap


def _ln(strike, iv):
    return {"strike": strike, "iv": iv, "bid": "1.0", "ask": "1.1", "volume": 1, "oi": 1}


@pytest.mark.django_db
def test_iv_summary_z_percentile_skew_term():
    now = datetime(2026, 4, 10, tzinfo=UTC)
    for d in range(30):
        iv = f"{0.28 + 0.01 * (d % 5):.3f}"
        _chain(
            "AAPL",
            when=now - timedelta(days=30 - d),
            expiries={"2026-05-15": {"calls": [_ln("100.00", iv)], "puts": [_ln("100.00", iv)]}},
        )
    _chain(
        "AAPL",
        when=now,
        expiries={
            "2026-05-15": {"calls": [_ln("100.00", "0.50")], "puts": [_ln("100.00", "0.53")]},
            "2026-06-19": {"calls": [_ln("100.00", "0.45")], "puts": [_ln("100.00", "0.45")]},
        },
    )
    out = iv_summary("AAPL", at=now)
    assert out["ticker"] == "AAPL"
    assert out["atm_iv"] == 0.50
    assert out["z"] is not None and out["z"] > 5
    assert out["percentile"] == 1.0
    assert out["skew"] == pytest.approx(0.03, abs=1e-9)
    assert out["term"]["shape"] == "backwardation"
    assert out["term"]["front_iv"] == 0.50 and out["term"]["next_iv"] == 0.45


@pytest.mark.django_db
def test_iv_summary_none_when_no_chain():
    assert iv_summary("ZZZZ", at=datetime(2026, 4, 10, tzinfo=UTC)) is None


@pytest.mark.django_db
def test_iv_summary_none_for_falsy_ticker():
    assert iv_summary("", at=datetime(2026, 4, 10, tzinfo=UTC)) is None


@patch("apps.market.services.intel.fetch_quotes")
def test_sector_rotation_drops_non_numeric_pct(mock_fq):
    mock_fq.return_value = {"XLK": {"pct_change": "N/A"}, "XLF": {"pct_change": 1.0}}
    out = sector_rotation()
    assert [r["etf"] for r in out["ranked"]] == ["XLF"]
