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
