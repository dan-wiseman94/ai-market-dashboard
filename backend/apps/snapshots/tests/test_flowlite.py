"""Tests for apps.snapshots.services.flowlite — the volume-based flow-pressure proxy.

Field names confirmed against apps.market.models.OptionChainSnapshot:
  - ticker column: `ticker`
  - JSON payload column holding the {expiry: {calls, puts}} dict: `payload["expiries"]`
    (the model's own `expiries` field is a flat list of expiry-date keys, not the dict)
  - capture-timestamp column: `fetched_at`
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.market.models import OHLCBar, OptionChainSnapshot
from apps.snapshots.services.flowlite import PROXY_NOTE, build_flowlite_payload

pytestmark = pytest.mark.django_db


def _seed_flat_then_spike(ticker: str, *, window: int = 20, flat_volume: int = 1_000_000) -> None:
    """Seed `window` flat-volume daily bars, then one 3-sigma-spike bar as the newest.

    pstdev of a set of identical values is 0, so we nudge every other flat bar by a
    tiny alternating amount to give the history a nonzero (but small) stdev, then
    make the spike bar large enough to clear z > 2 by a wide margin.
    """
    now = datetime.now(UTC)
    base_price = Decimal("450")
    # Oldest -> newest: window historical bars (i = window .. 1 days ago), then the
    # spike bar at i=0 (today, most recent).
    for i in range(window, 0, -1):
        wobble = 1_000 if i % 2 == 0 else -1_000
        OHLCBar.objects.create(
            ticker=ticker.upper(),
            timeframe="1d",
            open=base_price,
            high=base_price + 1,
            low=base_price - 1,
            close=base_price,
            volume=flat_volume + wobble,
            ts=now - timedelta(days=i),
        )
    OHLCBar.objects.create(
        ticker=ticker.upper(),
        timeframe="1d",
        open=base_price,
        high=base_price + 1,
        low=base_price - 1,
        close=base_price,
        volume=flat_volume * 5,
        ts=now,
    )


def _chain_snapshot(ticker: str, *, volume_ratio_bias: str, fetched_offset: timedelta) -> None:
    """Create an OptionChainSnapshot whose put/call volume ratio differs by bias.

    "low" -> more call volume than put volume (ratio < 1)
    "high" -> more put volume than call volume (ratio > 1)
    """
    if volume_ratio_bias == "low":
        call_volume, put_volume = 400, 100
    else:
        call_volume, put_volume = 100, 400
    expiries = {
        "2026-10-16": {
            "calls": [{"strike": "450.00", "volume": call_volume, "oi": 1000}],
            "puts": [{"strike": "450.00", "volume": put_volume, "oi": 1000}],
        },
    }
    snap = OptionChainSnapshot.objects.create(
        ticker=ticker.upper(),
        expiries=list(expiries.keys()),
        payload={"ticker": ticker.upper(), "expiries": expiries},
    )
    # fetched_at is auto_now_add; backdate the prior row so ordering is deterministic.
    OptionChainSnapshot.objects.filter(pk=snap.pk).update(
        fetched_at=datetime.now(UTC) - fetched_offset
    )


class TestBuildFlowlitePayload:
    def test_proxy_note_always_present(self):
        payload = build_flowlite_payload(watchlist_tickers=[], primary="SPY")
        assert payload["proxy_note"] == PROXY_NOTE

    def test_empty_db_degrades_to_empty_lists_and_none_delta(self):
        payload = build_flowlite_payload(watchlist_tickers=["SPY"], primary="SPY")
        assert payload == {
            "proxy_note": PROXY_NOTE,
            "volume_z": [],
            "put_call_delta": None,
            "unusual": [],
        }

    def test_volume_spike_surfaces_as_top_zscore(self):
        _seed_flat_then_spike("SPY")
        payload = build_flowlite_payload(watchlist_tickers=["SPY"], primary="SPY")
        assert payload["volume_z"], "expected at least one volume_z row"
        top = payload["volume_z"][0]
        assert top["ticker"] == "SPY"
        assert top["z"] > 2

    def test_volume_z_sorted_by_absolute_z_descending(self):
        _seed_flat_then_spike("SPY", flat_volume=1_000_000)
        _seed_flat_then_spike("QQQ", flat_volume=500_000)
        payload = build_flowlite_payload(watchlist_tickers=["SPY", "QQQ"], primary="SPY")
        zs = [abs(r["z"]) for r in payload["volume_z"]]
        assert zs == sorted(zs, reverse=True)

    def test_put_call_delta_is_latest_minus_prior_ratio(self):
        # Prior fetch (older): call-heavy -> low ratio. Latest fetch (newer): put-heavy -> high ratio.
        _chain_snapshot("SPY", volume_ratio_bias="low", fetched_offset=timedelta(hours=2))
        _chain_snapshot("SPY", volume_ratio_bias="high", fetched_offset=timedelta(hours=0))
        payload = build_flowlite_payload(watchlist_tickers=["SPY"], primary="SPY")
        delta = payload["put_call_delta"]
        assert delta is not None
        assert delta["ticker"] == "SPY"
        assert delta["latest"] == pytest.approx(400 / 100)
        assert delta["prior"] == pytest.approx(100 / 400)
        assert delta["delta"] == pytest.approx(delta["latest"] - delta["prior"])

    def test_put_call_delta_none_with_fewer_than_two_snapshots(self):
        _chain_snapshot("SPY", volume_ratio_bias="low", fetched_offset=timedelta(hours=0))
        payload = build_flowlite_payload(watchlist_tickers=["SPY"], primary="SPY")
        assert payload["put_call_delta"] is None

    def test_unusual_is_capped_at_three(self):
        payload = build_flowlite_payload(watchlist_tickers=["SPY"], primary="SPY")
        assert len(payload["unusual"]) <= 3

    def test_unusual_swallows_exceptions_to_empty_list(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("apps.analytics.services.unusual_options.unusual_options", _boom)
        payload = build_flowlite_payload(watchlist_tickers=["SPY"], primary="SPY")
        assert payload["unusual"] == []
