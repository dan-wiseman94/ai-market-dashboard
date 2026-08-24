"""VIX term-structure deltas in the snapshot diff (observer diff mode reads this)."""

from __future__ import annotations

from apps.snapshots.diff import diff_sections


def _payload(spot_last=15.2, front_last=16.8, contango=6.55, structure="contango") -> dict:
    return {
        "spot": {"symbol": "$VIX", "last": spot_last, "pct_change": None},
        "front": {"symbol": "/VXU26", "expiry": "2026-09-16", "last": front_last},
        "second": {"symbol": "/VXV26", "expiry": "2026-10-21", "last": 17.9},
        "contango_pct": contango,
        "structure": structure,
    }


def test_structure_flip_is_reported() -> None:
    out = diff_sections(
        {"vix": _payload()},
        {"vix": _payload(contango=-4.0, structure="backwardation")},
    )
    assert "**vix**" in out
    assert "- structure: contango → backwardation" in out
    assert "- contango: +6.55% → -4.00%" in out


def test_spot_and_front_moves_reported_above_noise() -> None:
    out = diff_sections(
        {"vix": _payload()},
        {"vix": _payload(spot_last=17.0, front_last=18.0)},
    )
    assert "- spot ($VIX): 15.2 → 17 (+11.84%)" in out
    assert "- front (/VXU26): 16.8 → 18 (+7.14%)" in out


def test_flat_vix_produces_no_delta() -> None:
    out = diff_sections({"vix": _payload()}, {"vix": _payload()})
    assert out == "No meaningful changes."


def test_sub_noise_moves_and_missing_legs_are_silent() -> None:
    prev = _payload()
    curr = _payload(spot_last=15.21)  # ~0.07% — below the 0.5% noise floor
    curr["front"] = None
    curr["contango_pct"] = None
    curr["structure"] = None
    assert diff_sections({"vix": prev}, {"vix": curr}) == "No meaningful changes."
