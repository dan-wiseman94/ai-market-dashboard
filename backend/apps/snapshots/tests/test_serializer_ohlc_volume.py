"""Cash indices ($SPX, $TNX, ...) don't trade — providers truthfully report
volume 0 on every bar. The rendered CSV must omit the volume column (with an
explicit note) instead of shipping rows of zeros the AI reads as a broken feed.
"""

from apps.snapshots.serializer import _render_ohlc


def _bar(minute: int, volume) -> dict:
    b = {
        "ts": f"2026-07-27T13:{minute:02d}:00+00:00",
        "open": 1,
        "high": 2,
        "low": 1,
        "close": 2,
    }
    if volume is not None:
        b["volume"] = volume
    return b


def test_all_zero_volume_omits_column_with_note():
    out = _render_ohlc({"ticker": "$SPX", "timeframe": "1m", "bars": [_bar(0, 0), _bar(1, 0)]})
    csv_block = out.split("```csv")[1].split("```")[0]
    assert "ts,open,high,low,close\n" in csv_block
    assert "volume" not in csv_block
    assert "no traded volume" in out


def test_real_volume_keeps_column():
    out = _render_ohlc({"ticker": "SPY", "timeframe": "1m", "bars": [_bar(0, 100), _bar(1, 200)]})
    assert "ts,open,high,low,close,volume" in out
    assert "no traded volume" not in out


def test_missing_volume_key_treated_as_absent():
    out = _render_ohlc({"ticker": "$TNX", "timeframe": "1d", "bars": [_bar(0, None)]})
    csv_block = out.split("```csv")[1].split("```")[0]
    assert "ts,open,high,low,close\n" in csv_block
    assert "volume" not in csv_block
    assert "no traded volume" in out


def test_mixed_zero_and_real_volume_keeps_column():
    # A thin session with one real print is not an index — keep the column.
    out = _render_ohlc({"ticker": "XYZ", "timeframe": "1m", "bars": [_bar(0, 0), _bar(1, 5)]})
    assert "ts,open,high,low,close,volume" in out
    assert "no traded volume" not in out
