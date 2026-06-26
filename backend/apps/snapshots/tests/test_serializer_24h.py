from apps.snapshots.serializer import _render_news, _render_ohlc

_BAR = {"ts": "2026-05-28T14:00:00+00:00", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}


def test_render_ohlc_24h_blended_header():
    md = _render_ohlc(
        {
            "ticker": "SPY",
            "timeframe": "1m",
            "window": "24h",
            "coarse_timeframe": "5m",
            "bars": [_BAR],
        }
    )
    assert "last 24h" in md
    assert "1m current session, 5m prior" in md


def test_render_ohlc_24h_single_resolution_header():
    md = _render_ohlc({"ticker": "SPY", "timeframe": "5m", "window": "24h", "bars": [_BAR]})
    assert "last 24h" in md
    assert "current session" not in md


def test_render_news_always_24h_label():
    md = _render_news({"items": []})
    assert "last 24h" in md.lower()
    assert "overnight" not in md.lower()
