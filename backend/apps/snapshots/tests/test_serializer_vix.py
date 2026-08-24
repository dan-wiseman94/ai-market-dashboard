"""VIX term-structure rendering for the AI payload.

Calls the private renderer directly to avoid needing a full Snapshot DB row
(same pattern as test_serializer_overnight.py); one full-flow test covers the
failed-section title.
"""

from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _render_vix, serialize_for_ai


def _payload(**extra) -> dict:
    base = {
        "spot": {"symbol": "$VIX", "last": 15.2, "pct_change": -3.1},
        "front": {
            "symbol": "/VXU26",
            "expiry": "2026-09-16",
            "continuous": False,
            "last": 16.8,
            "pct_change": -2.0,
            "basis": 1.6,
            "basis_pct": 10.53,
        },
        "second": {"symbol": "/VXV26", "expiry": "2026-10-21", "last": 17.9, "pct_change": -1.1},
        "contango_pct": 6.55,
        "structure": "contango",
    }
    base.update(extra)
    return base


def test_render_vix_full():
    assert _render_vix(_payload()) == (
        "## VIX term structure\n"
        "- Spot $VIX: 15.20 (-3.10%)\n"
        "- Front /VXU26 (exp 2026-09-16): 16.80 (-2.00%), basis +1.60 (+10.53% vs spot)\n"
        "- Second /VXV26 (exp 2026-10-21): 17.90 (-1.10%)\n"
        "- Structure: contango (+6.55% front→second)"
    )


def test_render_vix_continuous_front_has_no_expiry():
    payload = _payload(
        front={
            "symbol": "/VX",
            "expiry": None,
            "continuous": True,
            "last": 16.5,
            "pct_change": 0.2,
            "basis": 1.3,
            "basis_pct": 8.55,
        }
    )
    out = _render_vix(payload)
    assert "- Front /VX (continuous): 16.50 (+0.20%), basis +1.30 (+8.55% vs spot)" in out
    assert "exp" not in out.split("\n")[2]


def test_render_vix_spot_only_with_note():
    payload = _payload(
        front=None,
        second=None,
        contango_pct=None,
        structure=None,
        note="VIX futures unavailable (requires Schwab connection)",
    )
    out = _render_vix(payload)
    assert out == (
        "## VIX term structure\n"
        "- Spot $VIX: 15.20 (-3.10%)\n"
        "_(VIX futures unavailable (requires Schwab connection))_"
    )
    assert "Front" not in out
    assert "Structure" not in out


def test_render_vix_flat_structure():
    payload = _payload(contango_pct=0.0, structure="flat")
    assert "- Structure: flat (+0.00% front→second)" in _render_vix(payload)


def test_render_vix_missing_leg_values_render_as_dashes():
    payload = _payload(
        spot=None,
        front={
            "symbol": "/VXU26",
            "expiry": "2026-09-16",
            "continuous": False,
            "last": None,
            "pct_change": None,
            "basis": None,
            "basis_pct": None,
        },
        contango_pct=None,
        structure=None,
    )
    out = _render_vix(payload)
    assert "- Front /VXU26 (exp 2026-09-16): —" in out
    assert "Spot" not in out


@pytest.mark.parametrize("payload", [{}, None, "nonsense"])
def test_render_vix_degenerate_payload_is_explicit_not_empty(payload):
    assert _render_vix(payload) == "## VIX term structure\n_(empty)_"


@pytest.mark.django_db
def test_done_vix_section_renders_markdown_in_full_flow():
    # Pins the _RENDERERS["vix"] registration: without it, _render_section
    # falls back to a raw ```json dict dump on every snapshot.
    p = TradingProfile.objects.create(name="P2", style="x")
    s = Snapshot.objects.create(profile=p, includes=["vix"], source="manual", status="ready")
    SnapshotSection.objects.create(snapshot=s, kind="vix", status="done", payload=_payload())
    out = serialize_for_ai(s)
    assert "## VIX term structure" in out
    assert "- Spot $VIX: 15.20 (-3.10%)" in out
    assert "- Structure: contango (+6.55% front→second)" in out
    assert "```json" not in out


@pytest.mark.django_db
def test_failed_vix_section_renders_unavailable_with_proper_title():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["vix"], source="manual", status="ready")
    SnapshotSection.objects.create(
        snapshot=s, kind="vix", status="failed", payload={}, error="SchwabNotConnectedError: x"
    )
    out = serialize_for_ai(s)
    assert "## VIX term structure" in out
    assert "unavailable" in out
    assert "## Vix" not in out
