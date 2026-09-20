"""Tests for the RS + sector-rotation lines added to _render_breadth.

Calls the private renderer directly to avoid needing a full Snapshot DB row.
All rendered-string assertions are derived from the payload values by hand.
"""

from __future__ import annotations

from apps.snapshots.serializer import _render_breadth


def _base_payload(**extra) -> dict:
    """Minimal valid breadth payload (original fields only, no RS/rotation)."""
    return {
        "spx_last": 5000.0,
        "qqq_last": 430.0,
        "vix_last": 15.5,
        "sectors": {"XLK": 210.0, "XLF": 45.0},
        "breadth": {"$ADVN": 1800.0},
        **extra,
    }


def _rs_payload(*, int_keys: bool = True) -> dict:
    """Relative-strength dict with 1d and 5d windows.

    rs values (hand-verified):
      1d rs = +7.96 → rendered "+7.96%"
      5d rs = +72.22 → rendered "+72.22%"
    """
    windows: dict = {
        1: {"ticker_pct": 10.0, "benchmark_pct": 2.04, "rs": 7.96},
        5: {"ticker_pct": 83.33, "benchmark_pct": 11.11, "rs": 72.22},
        20: {"ticker_pct": None, "benchmark_pct": None, "rs": None},
    }
    if not int_keys:
        # Simulate JSON round-trip: keys become strings.
        windows = {str(k): v for k, v in windows.items()}
    return {"ticker": "NVDA", "benchmark": "$SPX", "windows": windows}


def test_render_breadth_without_rs_unchanged():
    """Payload with no relative_strength or sector_rotation renders the base breadth block."""
    payload = _base_payload()
    result = _render_breadth(payload)
    assert result.startswith("## Market breadth")
    assert "SPX: 5000.00" in result
    assert "QQQ: 430.00" in result
    assert "VIX: 15.50" in result
    assert "| XLK | 210.00 |" in result  # sector table row
    assert "Relative strength" not in result
    assert "- Sector rotation" not in result  # old leader/laggard line gone


def test_render_breadth_rs_none_no_rs_line():
    """relative_strength=None → no RS line."""
    payload = _base_payload(relative_strength=None)
    result = _render_breadth(payload)
    assert "Relative strength" not in result


def test_render_breadth_empty_rotation_no_rotation_line():
    """sector_rotation=[] → no rotation line."""
    payload = _base_payload(sector_rotation=[])
    result = _render_breadth(payload)
    assert "Sector rotation" not in result


def test_rs_line_rendered_with_int_keys():
    """RS line produced when relative_strength present with int keys.

    Hand-verified:
      1d rs=7.96  → "1d +7.96%"
      5d rs=72.22 → "5d +72.22%"
      20d rs=None → omitted
    Expected line: "- Relative strength (NVDA vs $SPX): 1d +7.96%, 5d +72.22%"
    """
    payload = _base_payload(relative_strength=_rs_payload(int_keys=True))
    result = _render_breadth(payload)
    assert "- Relative strength (NVDA vs $SPX): 1d +7.96%, 5d +72.22%" in result


def test_rs_line_omits_windows_with_none_rs():
    """Windows whose rs is None are omitted from the RS line (20d here)."""
    payload = _base_payload(relative_strength=_rs_payload(int_keys=True))
    result = _render_breadth(payload)
    assert "20d" not in result


def test_rs_line_rendered_with_str_keys():
    """RS line still rendered when window keys are strings (JSON round-trip case).

    Expected line unchanged: "- Relative strength (NVDA vs $SPX): 1d +7.96%, 5d +72.22%"
    """
    payload = _base_payload(relative_strength=_rs_payload(int_keys=False))
    result = _render_breadth(payload)
    assert "- Relative strength (NVDA vs $SPX): 1d +7.96%, 5d +72.22%" in result


def test_rs_line_skipped_when_all_rs_none():
    """No RS line when all windows have rs=None (e.g. benchmark missing)."""
    rs = {
        "ticker": "NVDA",
        "benchmark": "$SPX",
        "windows": {
            1: {"ticker_pct": 10.0, "benchmark_pct": None, "rs": None},
            5: {"ticker_pct": 83.0, "benchmark_pct": None, "rs": None},
        },
    }
    payload = _base_payload(relative_strength=rs)
    result = _render_breadth(payload)
    assert "Relative strength" not in result


def test_rotation_line_leader_and_laggard():
    """Sector table rows show return_pct from sector_rotation.

    Hand-verified from the intel test fixture:
      XLF return_pct=25.0  → "+25.00%"
      XLK return_pct=5.5556 → "+5.56%" (formatted to 2dp)
    Expected table rows with rotation data.
    """
    rotation = [
        {"sector": "XLF", "return_pct": 25.0, "rs": 13.89},
        {"sector": "XLK", "return_pct": 5.5556, "rs": -5.56},
    ]
    payload = _base_payload(sector_rotation=rotation)
    result = _render_breadth(payload)
    assert "| XLF | 45.00 | — | 25.00 | 13.89 |" in result
    assert "| XLK | 210.00 | — | 5.56 | -5.56 |" in result


def test_rotation_line_single_sector():
    """Single sector rotation row in table."""
    rotation = [{"sector": "XLF", "return_pct": 25.0, "rs": 13.89}]
    payload = _base_payload(sector_rotation=rotation)
    result = _render_breadth(payload)
    assert "| XLF | 45.00 | — | 25.00 | 13.89 |" in result


def test_rotation_negative_returns_formatted_correctly():
    """Negative return_pct is formatted correctly in table rows."""
    rotation = [
        {"sector": "XLF", "return_pct": -3.5, "rs": -14.61},
        {"sector": "XLK", "return_pct": -8.0, "rs": -19.11},
    ]
    payload = _base_payload(sector_rotation=rotation)
    result = _render_breadth(payload)
    # XLF is second in sectors dict, XLK is first; order follows sectors dict
    assert "| XLK | 210.00 | — | -8.00 | -19.11 |" in result
    assert "| XLF | 45.00 | — | -3.50 | -14.61 |" in result


def test_rs_and_rotation_both_rendered():
    """When both RS and rotation are present, RS line and sector table both appear."""
    rotation = [
        {"sector": "XLF", "return_pct": 25.0, "rs": 13.89},
        {"sector": "XLK", "return_pct": 5.56, "rs": -5.55},
    ]
    payload = _base_payload(
        relative_strength=_rs_payload(int_keys=True),
        sector_rotation=rotation,
    )
    result = _render_breadth(payload)
    assert "Relative strength" in result
    assert "| Sector | Last | 1d% | 5d% | RS vs SPX (5d) |" in result  # sector table header


def test_original_lines_present_alongside_intel():
    """Original SPX/QQQ/VIX/Breadth lines still rendered; Sectors now as table when intel is added."""
    rotation = [{"sector": "XLF", "return_pct": 25.0, "rs": 13.89}]
    payload = _base_payload(
        relative_strength=_rs_payload(int_keys=True),
        sector_rotation=rotation,
    )
    result = _render_breadth(payload)
    assert "SPX: 5000.00" in result
    assert "QQQ: 430.00" in result
    assert "VIX: 15.50" in result
    assert "| Sector | Last |" in result  # sector table header (replaces "Sectors:" line)
    assert "- Internals:" in result  # Breadth label changed to Internals


def _breadth_payload():
    return {
        "spx_last": 6500.0,
        "qqq_last": 560.0,
        "vix_last": 15.0,
        "index_complex": [
            {"symbol": "$SPX", "last": 6500.0, "pct_change": 0.4},
            {"symbol": "/ES", "last": 6510.0, "pct_change": 0.5},
        ],
        "dollar": {"symbol": "UUP", "last": 27.9, "pct_change": -0.2},
        "sectors": {"XLK": 231.4, "XLF": 45.1},
        "sector_pct": {"XLK": 1.2},
        "sector_rotation": [{"sector": "XLK", "return_pct": 2.5, "rs": 1.1}],
        "breadth": {"$ADVN": 2000, "$DECN": 900, "$UVOL": 5.1e9, "$DVOL": 2.2e9},
        "breadth_stats": {
            "pct_above_sma": {"20": {"above": 7, "n": 11, "pct": 63.6}},
            "highs": 2,
            "lows": 1,
            "hl_n": 11,
            "hl_window": 252,
            "min_span_sessions": 60,
        },
        "relative_strength": None,
        "factor_returns": {
            "windows": [1, 5, 20],
            "etfs": {"MTUM": {"5": 4.0}, "VLUE": {"5": 1.0}},
            "spreads": {"momentum_minus_value": {"5": 3.0}},
        },
    }


def test_render_breadth_full_desk_view():
    payload = _breadth_payload()
    out = _render_breadth(payload)
    assert "- Index complex: $SPX 6500.00 (0.40%), /ES 6510.00 (0.50%)" in out
    assert "- Dollar (UUP): 27.90 (-0.20%)" in out
    assert "| XLK | 231.40 | 1.20 | 2.50 | 1.10 |" in out  # sector table row
    assert "$UVOL" in out  # internals line
    assert ">20dSMA 64% (7/11)" in out
    assert "≤60-session span" in out  # real window, not 252
    assert "MTUM +4.00%" in out and "Mom-Val +3.00%" in out


def test_render_breadth_without_new_keys_still_renders():
    out = _render_breadth({"spx_last": 6500.0, "qqq_last": 560.0, "vix_last": 15.0})
    assert "- SPX: 6500.00" in out and "- VIX: 15.00" in out  # old payloads intact
