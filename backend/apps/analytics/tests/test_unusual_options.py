"""Unusual-options detector finds volume-vs-OI blowouts + IV z-score outliers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from apps.analytics.services.unusual_options import unusual_options
from apps.market.models import OptionChainSnapshot


def _mk_snapshot(ticker: str, *, when: datetime, calls: list[dict], puts: list[dict]):
    snap = OptionChainSnapshot.objects.create(
        ticker=ticker,
        expiries=["2026-05-15"],
        payload={
            "underlying_last": "100.00",
            "expiries": {"2026-05-15": {"calls": calls, "puts": puts}},
            "ticker": ticker,
        },
    )
    OptionChainSnapshot.objects.filter(id=snap.id).update(
        fetched_at=when.replace(tzinfo=UTC) if when.tzinfo is None else when,
    )
    return snap


def _line(strike: str, *, bid: str, ask: str, iv: str, volume: int, oi: int) -> dict:
    return {
        "strike": strike,
        "bid": bid,
        "ask": ask,
        "last": bid,
        "volume": volume,
        "oi": oi,
        "delta": "0.50",
        "gamma": "0.01",
        "theta": "-0.03",
        "vega": "0.12",
        "iv": iv,
    }


def test_flags_volume_over_open_interest(db) -> None:
    now = datetime(2026, 4, 10, tzinfo=UTC)
    # Some natural IV variation across the 30-day history so stdev > 0.
    for d in range(30):
        iv_val = f"{0.28 + 0.01 * (d % 5):.3f}"  # 0.28..0.32 cycle
        _mk_snapshot(
            "AAPL",
            when=now - timedelta(days=30 - d),
            calls=[_line("150", bid="1.0", ask="1.1", iv=iv_val, volume=100, oi=10_000)],
            puts=[],
        )
    _mk_snapshot(
        "AAPL",
        when=now,
        calls=[_line("150", bid="1.0", ask="1.1", iv="0.55", volume=20_000, oi=10_000)],
        puts=[],
    )

    flagged = unusual_options(ticker="AAPL", at=now)
    assert len(flagged) >= 1
    hit = flagged[0]
    assert hit["strike"] == "150"
    assert hit["side"] == "call"
    assert hit["volume_ratio"] == pytest.approx(2.0, rel=0.01)
    assert hit["iv_z"] is not None and hit["iv_z"] > 1.5


def test_no_unusual_when_within_ratios(db) -> None:
    now = datetime(2026, 4, 10, tzinfo=UTC)
    for d in range(30):
        _mk_snapshot(
            "AAPL",
            when=now - timedelta(days=30 - d),
            calls=[_line("150", bid="1.0", ask="1.1", iv="0.30", volume=100, oi=10_000)],
            puts=[],
        )
    _mk_snapshot(
        "AAPL",
        when=now,
        calls=[_line("150", bid="1.0", ask="1.1", iv="0.31", volume=200, oi=10_000)],
        puts=[],
    )
    flagged = unusual_options(ticker="AAPL", at=now)
    assert flagged == []


def test_handles_no_history_gracefully(db) -> None:
    now = datetime(2026, 4, 10, tzinfo=UTC)
    _mk_snapshot(
        "NEWTK",
        when=now,
        calls=[_line("10", bid="1.0", ask="1.1", iv="0.4", volume=50_000, oi=1_000)],
        puts=[],
    )
    out = unusual_options(ticker="NEWTK", at=now)
    assert len(out) == 1
    assert out[0]["iv_z"] is None
    assert out[0]["volume_ratio"] >= 3.0
