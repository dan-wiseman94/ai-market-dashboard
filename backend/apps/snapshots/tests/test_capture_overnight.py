from unittest.mock import MagicMock, patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture


@pytest.mark.django_db
def test_overnight_capture_enriches_sections_and_adds_board():
    profile = TradingProfile.objects.create(name="P", style="x")
    quotes_mock = MagicMock(
        return_value={"SPY": {"last": 100.0, "gap_pct": 2.0, "prior_close": 98.0}}
    )
    with (
        patch("apps.snapshots.services.fetch_quotes", quotes_mock),
        patch(
            "apps.snapshots.services.fetch_ohlc_overnight",
            return_value=[
                {
                    "ts": "2026-05-29T02:00:00+00:00",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 1.5,
                    "volume": 10,
                }
            ],
        ),
        patch(
            "apps.snapshots.services.fetch_news",
            return_value=[{"id": 1, "headline": "overnight h", "datetime": 1_700_000_000}],
        ),
        patch(
            "apps.snapshots.services.overnight_board",
            return_value={
                "futures": {"/ES": {"last": 5000.0, "gap_pct": 0.5}},
                "vol_rates": {},
                "overseas": {},
            },
        ),
    ):
        snap = capture(
            profile=profile,
            objective="o",
            includes=["quotes", "ohlc", "news"],
            watchlist_tickers=["SPY"],
            ohlc_ticker="SPY",
            ohlc_timeframe="1m",
            overnight=True,
        )

    assert snap.overnight is True
    assert "overnight" in snap.includes
    secs = {s.kind: s for s in snap.sections.all()}
    # board section created + done
    assert secs["overnight"].status == "done"
    assert secs["overnight"].payload["futures"]["/ES"]["last"] == 5000.0
    # quotes asked for gap context, gap fields present
    assert quotes_mock.call_args.kwargs.get("gap_context") is True
    assert secs["quotes"].payload["SPY"]["gap_pct"] == 2.0
    # ohlc widened + coarsened 1m -> 5m + window tag
    assert secs["ohlc"].payload["window"] == "overnight"
    assert secs["ohlc"].payload["timeframe"] == "5m"
    # news tagged overnight with a since timestamp
    assert secs["news"].payload["window"] == "overnight"
    assert "since" in secs["news"].payload


@pytest.mark.django_db
def test_default_capture_unchanged_when_overnight_false():
    profile = TradingProfile.objects.create(name="P", style="x")
    with (
        patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 100.0}}),
        patch("apps.snapshots.services.fetch_ohlc_session", return_value=[]),
    ):
        snap = capture(
            profile=profile,
            objective="o",
            includes=["quotes", "ohlc"],
            watchlist_tickers=["SPY"],
            ohlc_ticker="SPY",
            ohlc_timeframe="1m",
        )
    assert snap.overnight is False
    assert "overnight" not in snap.includes
    secs = {s.kind: s for s in snap.sections.all()}
    assert "window" not in secs["ohlc"].payload  # not widened
    assert secs["ohlc"].payload["timeframe"] == "1m"  # not coarsened
    assert set(secs["quotes"].payload["SPY"]) == {"last"}  # no gap fields
