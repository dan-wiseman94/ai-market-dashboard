"""Capture a snapshot that includes every M5 section type and assert payloads.

External calls to Schwab / Finnhub / Playwright are mocked at the SDK boundary.
"""
from unittest.mock import patch

import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import SnapshotImage
from apps.snapshots.services import capture


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


@pytest.mark.django_db
def test_full_m5_capture_emits_all_sections():
    profile = TradingProfile.objects.create(name="P", style="x")

    fake_chain = {"ticker": "SPY", "underlying_last": "521.30",
                  "expiries": {"2026-04-25": {"calls": [], "puts": []}}}
    fake_news = [{"id": 1, "headline": "Fed", "summary": "x", "url": "https://x",
                  "source": "R", "datetime": 1700000000, "related": "SPY"}]

    def fake_render(ticker, timeframe, bars, *, snapshot_id):
        return SnapshotImage.objects.create(
            snapshot_id=snapshot_id, kind="server_render",
            data=PNG, caption=f"{ticker} {timeframe}",
        )

    # Patch at consumption site (apps.snapshots.services.*) — see test_capture_extended.py
    # for the rationale (lambdas in _FETCHERS close over the imported names).
    with patch("apps.snapshots.services.fetch_chain", return_value=fake_chain), \
         patch("apps.snapshots.services.fetch_news", return_value=fake_news), \
         patch("apps.snapshots.services.render_chart_png", side_effect=fake_render), \
         patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 521.3}}), \
         patch("apps.snapshots.services.fetch_ohlc", return_value=[]), \
         patch("apps.snapshots.services.fetch_positions", return_value=[]), \
         patch("apps.snapshots.services.fetch_market_context", return_value={}):
        snap = capture(
            profile=profile, objective="full m5",
            includes=["quotes", "ohlc", "positions", "breadth", "chain", "news", "image", "notes"],
            watchlist_tickers=["SPY"],
            ohlc_ticker="SPY", ohlc_timeframe="5m", ohlc_bars=60,
        )

    assert snap.status == "ready"
    kinds = {s.kind: s.status for s in snap.sections.all()}
    for k in ["quotes", "ohlc", "positions", "breadth", "chain", "news", "image", "notes"]:
        assert kinds.get(k) == "done", f"section {k} not done: {kinds}"
