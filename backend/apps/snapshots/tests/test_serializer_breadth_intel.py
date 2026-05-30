"""Tests for the RS + sector-rotation lines added to _render_breadth.

Calls the private renderer directly to avoid needing a full Snapshot DB row.
All rendered-string assertions are derived from the payload values by hand.
"""

from __future__ import annotations

from apps.snapshots.serializer import _render_breadth

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Backward-compat: payload without RS/rotation keys
# ---------------------------------------------------------------------------


def test_render_breadth_without_rs_unchanged():
    """Payload with no relative_strength or sector_rotation renders exactly as before."""
    payload = _base_payload()
    result = _render_breadth(payload)
    assert result.startswith("## Market breadth")
    assert "SPX: 5000.00" in result
    assert "QQQ: 430.00" in result
    assert "VIX: 15.50" in result
    assert "Sectors:" in result
    assert "Relative strength" not in result
    assert "Sector rotation" not in result


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


# ---------------------------------------------------------------------------
# RS line — integer window keys (in-memory, no JSON round-trip)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# RS line — string window keys (JSON round-trip simulation)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Sector rotation line
# ---------------------------------------------------------------------------


def test_rotation_line_leader_and_laggard():
    """Rotation line shows leader (XLF +25.00%) and laggard (XLK +5.56%).

    Hand-verified from the intel test fixture:
      XLF return_pct=25.0  → "+25.00%"
      XLK return_pct=5.5556 → "+5.56%" (formatted to 2dp)
    Expected: "- Sector rotation (2 sectors): leader XLF +25.00%, laggard XLK +5.56%"
    """
    rotation = [
        {"sector": "XLF", "return_pct": 25.0, "rs": 13.89},
        {"sector": "XLK", "return_pct": 5.5556, "rs": -5.56},
    ]
    payload = _base_payload(sector_rotation=rotation)
    result = _render_breadth(payload)
    assert "- Sector rotation (2 sectors): leader XLF +25.00%, laggard XLK +5.56%" in result


def test_rotation_line_single_sector():
    """With only one sector, leader and laggard are the same entry."""
    rotation = [{"sector": "XLF", "return_pct": 25.0, "rs": 13.89}]
    payload = _base_payload(sector_rotation=rotation)
    result = _render_breadth(payload)
    assert "- Sector rotation (1 sectors): leader XLF +25.00%, laggard XLF +25.00%" in result


def test_rotation_negative_returns_formatted_correctly():
    """Negative return_pct is formatted with a leading minus sign."""
    rotation = [
        {"sector": "XLE", "return_pct": -3.5, "rs": -14.61},
        {"sector": "XLK", "return_pct": -8.0, "rs": -19.11},
    ]
    payload = _base_payload(sector_rotation=rotation)
    result = _render_breadth(payload)
    # leader is XLE (higher rs -14.61), laggard is XLK (lower rs -19.11)
    assert "leader XLE -3.50%" in result
    assert "laggard XLK -8.00%" in result


# ---------------------------------------------------------------------------
# Both RS and rotation present together
# ---------------------------------------------------------------------------


def test_rs_and_rotation_both_rendered():
    """When both RS and rotation are present, both lines appear."""
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
    assert "Sector rotation" in result


def test_original_lines_present_alongside_intel():
    """Original SPX/QQQ/VIX/Sectors/Breadth lines still rendered when intel is added."""
    rotation = [{"sector": "XLF", "return_pct": 25.0, "rs": 13.89}]
    payload = _base_payload(
        relative_strength=_rs_payload(int_keys=True),
        sector_rotation=rotation,
    )
    result = _render_breadth(payload)
    assert "SPX: 5000.00" in result
    assert "QQQ: 430.00" in result
    assert "VIX: 15.50" in result
    assert "Sectors:" in result
    assert "Breadth:" in result
