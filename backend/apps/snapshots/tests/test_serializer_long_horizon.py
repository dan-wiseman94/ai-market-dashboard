"""Tests for the long-horizon OHLC summary in the AI payload serializer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.market.models import OHLCBar
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _long_horizon_summary, _render_ohlc, serialize_for_ai


def _ohlc_payload(ticker: str = "SPY", timeframe: str = "1m") -> dict:
    """Build a minimal OHLC payload for testing."""
    return {
        "ticker": ticker,
        "timeframe": timeframe,
        "bars": [
            {
                "ts": "2026-05-23T09:30:00+00:00",
                "open": 450,
                "high": 451,
                "low": 449,
                "close": 450.5,
                "volume": 1000,
            }
        ],
    }


def _seed_daily_bars(ticker: str, days: int = 60) -> None:
    """Seed ~60 daily OHLCBar rows for a given ticker.

    Creates daily bars with a price ranging from 450-500, with data points
    spread backwards from today.
    """
    now = datetime.now(UTC)
    for i in range(days):
        ts = now - timedelta(days=i)
        # Vary price slightly to make returns meaningful
        base_price = 450 + (i % 50)
        OHLCBar.objects.create(
            ticker=ticker.upper(),
            timeframe="1d",
            open=Decimal(str(base_price)),
            high=Decimal(str(base_price + 1)),
            low=Decimal(str(base_price - 1)),
            close=Decimal(str(base_price + 0.5)),
            volume=1000000,
            ts=ts,
        )


class TestLongHorizonSummary:
    """Tests for _long_horizon_summary function."""

    def test_long_horizon_summary_returns_empty_when_ticker_is_none(self):
        """_long_horizon_summary returns empty string when ticker is None."""
        result = _long_horizon_summary(None)
        assert result == ""

    def test_long_horizon_summary_returns_empty_when_ticker_is_empty_string(self):
        """_long_horizon_summary returns empty string when ticker is empty."""
        result = _long_horizon_summary("")
        assert result == ""

    @pytest.mark.django_db
    def test_long_horizon_summary_returns_empty_with_few_bars(self):
        """_long_horizon_summary returns empty string when fewer than 20 daily bars exist."""
        _seed_daily_bars("SPY", days=10)
        result = _long_horizon_summary("SPY")
        assert result == ""

    @pytest.mark.django_db
    def test_long_horizon_summary_with_sufficient_bars(self):
        """_long_horizon_summary returns formatted block with 60+ daily bars."""
        _seed_daily_bars("SPY", days=60)
        result = _long_horizon_summary("SPY")

        assert result != ""
        assert "**Longer horizon (stored daily bars):**" in result
        assert "60-session high" in result
        assert "-session high" in result  # Check for the generic pattern
        assert "% off high" in result
        assert "vs 20dSMA" in result

    @pytest.mark.django_db
    def test_long_horizon_summary_includes_smas(self):
        """_long_horizon_summary includes 20d/50d/200d SMA calculations."""
        _seed_daily_bars("SPY", days=200)
        result = _long_horizon_summary("SPY")

        # Should have all three SMAs since we have 200 bars
        assert "vs 20dSMA" in result
        assert "vs 50dSMA" in result
        assert "vs 200dSMA" in result

    @pytest.mark.django_db
    def test_long_horizon_summary_excludes_unavailable_smas(self):
        """_long_horizon_summary only includes SMAs with sufficient data."""
        _seed_daily_bars("SPY", days=30)
        result = _long_horizon_summary("SPY")

        # Should have 20d SMA but not 50d or 200d
        assert "vs 20dSMA" in result
        assert "vs 50dSMA" not in result
        assert "vs 200dSMA" not in result

    @pytest.mark.django_db
    def test_long_horizon_summary_bounds_to_captured_at(self):
        """Bars at/after captured_at must never leak into the summary — eval
        replay (apps.analytics.services.aieval.replay_one) re-serializes FROZEN
        past snapshots and an unbounded query would leak the outcome window."""
        captured_at = datetime(2026, 6, 1, 16, 0, tzinfo=UTC)

        # 25 pre-capture daily bars, most-recent (closest to captured_at) first:
        # closes 474, 473, ..., 450 at ts = captured_at, captured_at-1d, ...
        for i in range(25):
            close = 474 - i
            OHLCBar.objects.create(
                ticker="SPY",
                timeframe="1d",
                open=Decimal(str(close)),
                high=Decimal(str(close + 1)),
                low=Decimal(str(close - 1)),
                close=Decimal(str(close)),
                volume=1_000_000,
                ts=captured_at - timedelta(days=i),
            )
        # A post-capture bar with an extreme close — a bounded query must never see it.
        OHLCBar.objects.create(
            ticker="SPY",
            timeframe="1d",
            open=Decimal("9999"),
            high=Decimal("9999"),
            low=Decimal("9999"),
            close=Decimal("9999"),
            volume=1_000_000,
            ts=captured_at + timedelta(days=1),
        )

        bounded = _long_horizon_summary("SPY", captured_at)
        unbounded = _long_horizon_summary("SPY", None)

        # Bounded: high/low/returns reflect ONLY the 25 pre-capture bars.
        assert "9999" not in bounded
        assert "25-session high 474.00 / low 450.00" in bounded
        assert "returns 5d +1.1%, 20d +4.4%" in bounded

        # Unbounded (back-compat / no snapshot context): sees the future outlier.
        assert "9999" in unbounded
        assert "26-session high 9999.00" in unbounded

    def test_long_horizon_summary_captured_at_none_is_back_compat(self):
        """Explicitly passing captured_at=None (the default) behaves like the
        pre-fix unbounded call — no DB access here, just the signature check."""
        assert _long_horizon_summary(None, None) == ""
        assert _long_horizon_summary("", None) == ""


class TestRenderOhlcWithLongHorizonSummary:
    """Tests for _render_ohlc with long-horizon summary appended."""

    @pytest.mark.django_db
    def test_render_ohlc_includes_long_horizon_block_when_bars_exist(self):
        """_render_ohlc appends the long-horizon block when sufficient daily bars exist."""
        _seed_daily_bars("SPY", days=60)
        payload = _ohlc_payload("SPY")
        result = _render_ohlc(payload)

        assert "**Longer horizon (stored daily bars):**" in result
        assert "60-session high" in result
        assert "vs 20dSMA" in result

    @pytest.mark.django_db
    def test_render_ohlc_omits_long_horizon_block_without_bars(self):
        """_render_ohlc does not include the long-horizon block when daily bars are missing."""
        payload = _ohlc_payload("SPY")
        result = _render_ohlc(payload)

        # Block should NOT appear without bars
        assert "**Longer horizon (stored daily bars):**" not in result
        assert "vs 20dSMA" not in result

    @pytest.mark.django_db
    def test_render_ohlc_without_stored_bars_unchanged(self):
        """Existing OHLC rendering is unchanged when no stored bars exist."""
        payload = _ohlc_payload("SPY")
        result = _render_ohlc(payload)

        # Core OHLC structure should still be present
        assert "## OHLC" in result
        assert "ts,open,high,low,close,volume" in result
        assert "2026-05-23" in result

    @pytest.mark.django_db
    def test_render_ohlc_preserves_existing_sections(self):
        """Appending long-horizon summary doesn't affect prior sections."""
        _seed_daily_bars("SPY", days=60)
        payload = _ohlc_payload("SPY")
        result = _render_ohlc(payload)

        # Should have both the CSV and the summary
        assert "ts,open,high,low,close,volume" in result
        assert "**Longer horizon (stored daily bars):**" in result
        # Summary should come after CSV
        csv_idx = result.find("ts,open,high,low,close,volume")
        summary_idx = result.find("**Longer horizon")
        assert csv_idx < summary_idx

    @pytest.mark.django_db
    def test_render_ohlc_passes_captured_at_bound_to_long_horizon(self):
        """captured_at flows from _render_ohlc into the long-horizon bar query bound."""
        captured_at = datetime(2026, 6, 1, tzinfo=UTC)
        for i in range(25):
            close = 474 - i
            OHLCBar.objects.create(
                ticker="SPY",
                timeframe="1d",
                open=Decimal(str(close)),
                high=Decimal(str(close + 1)),
                low=Decimal(str(close - 1)),
                close=Decimal(str(close)),
                volume=1_000_000,
                ts=captured_at - timedelta(days=i),
            )
        OHLCBar.objects.create(
            ticker="SPY",
            timeframe="1d",
            open=Decimal("9999"),
            high=Decimal("9999"),
            low=Decimal("9999"),
            close=Decimal("9999"),
            volume=1_000_000,
            ts=captured_at + timedelta(days=1),
        )
        payload = _ohlc_payload("SPY")

        bounded = _render_ohlc(payload, captured_at=captured_at)
        unbounded = _render_ohlc(payload)

        assert "9999" not in bounded
        assert "9999" in unbounded


class TestSerializeForAiWithLongHorizonSummary:
    """End-to-end tests for serialize_for_ai with long-horizon summary."""

    @pytest.mark.django_db
    def test_serialize_for_ai_includes_long_horizon_in_full_path(self):
        """Full serialize_for_ai path includes the long-horizon block when appropriate."""
        _seed_daily_bars("SPY", days=60)

        profile = TradingProfile.objects.create(name="long-horizon-test", style="s")
        snap = Snapshot.objects.create(profile=profile, includes=["ohlc"], status="ready")
        SnapshotSection.objects.create(
            snapshot=snap,
            kind="ohlc",
            status="done",
            payload=_ohlc_payload("SPY"),
        )

        result = serialize_for_ai(snap)

        assert "**Longer horizon (stored daily bars):**" in result
        assert "60-session high" in result
        assert "vs 20dSMA" in result

    @pytest.mark.django_db
    def test_serialize_for_ai_omits_long_horizon_without_bars(self):
        """serialize_for_ai does not include long-horizon block without stored bars."""
        profile = TradingProfile.objects.create(name="no-bars-test", style="s")
        snap = Snapshot.objects.create(profile=profile, includes=["ohlc"], status="ready")
        SnapshotSection.objects.create(
            snapshot=snap,
            kind="ohlc",
            status="done",
            payload=_ohlc_payload("SPY"),
        )

        result = serialize_for_ai(snap)

        assert "**Longer horizon (stored daily bars):**" not in result
        # But should still have the intraday OHLC
        assert "## OHLC" in result

    @pytest.mark.django_db
    def test_serialize_for_ai_long_horizon_bounded_to_snapshot_captured_at(self):
        """The full serialize_for_ai path must not leak bars captured after the
        snapshot's own captured_at — the eval harness (apps.analytics.services.aieval
        .replay_one) re-serializes FROZEN past snapshots and relies on this bound to
        stay look-ahead-safe."""
        captured_at = datetime(2026, 6, 1, tzinfo=UTC)
        for i in range(25):
            close = 474 - i
            OHLCBar.objects.create(
                ticker="SPY",
                timeframe="1d",
                open=Decimal(str(close)),
                high=Decimal(str(close + 1)),
                low=Decimal(str(close - 1)),
                close=Decimal(str(close)),
                volume=1_000_000,
                ts=captured_at - timedelta(days=i),
            )
        # A future bar (relative to captured_at) that must never leak into the prompt.
        OHLCBar.objects.create(
            ticker="SPY",
            timeframe="1d",
            open=Decimal("9999"),
            high=Decimal("9999"),
            low=Decimal("9999"),
            close=Decimal("9999"),
            volume=1_000_000,
            ts=captured_at + timedelta(days=1),
        )

        profile = TradingProfile.objects.create(name="bound-test", style="s")
        snap = Snapshot.objects.create(profile=profile, includes=["ohlc"], status="ready")
        # captured_at is auto_now_add=True; override it to the fixed time above.
        Snapshot.objects.filter(pk=snap.pk).update(captured_at=captured_at)
        snap.refresh_from_db()
        SnapshotSection.objects.create(
            snapshot=snap,
            kind="ohlc",
            status="done",
            payload=_ohlc_payload("SPY"),
        )

        result = serialize_for_ai(snap)

        assert "**Longer horizon (stored daily bars):**" in result
        assert "9999" not in result
        assert "25-session high 474.00" in result
