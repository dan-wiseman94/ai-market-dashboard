"""Enforces ≤600KB per visual baseline.

600KB, not 500: the densest legitimate page (AI Providers settings — three
stacked provider-config cards on a dark theme) renders ~534KB at 1280x800 even
with the standard masks applied. 500KB was too tight for it; 600KB still flags a
real mask leak, which balloons a baseline into the megabytes.
"""

from __future__ import annotations

from pathlib import Path

MAX_BYTES = 600 * 1024


def test_no_baseline_exceeds_600kb() -> None:
    root = Path("e2e/visual/__screenshots__")
    if not root.exists():
        return
    oversize = [p for p in root.rglob("*.png") if p.stat().st_size > MAX_BYTES]
    assert not oversize, f"baselines exceeding 600KB: {[str(p) for p in oversize]}"
