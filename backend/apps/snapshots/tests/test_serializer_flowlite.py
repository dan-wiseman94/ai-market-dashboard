"""Flow-proxy (volume-based) section rendering for the AI payload.

`_render_flowlite` is a pure function (no DB access) — unlike `_render_fed`,
these tests don't need `django_db` except for the full-flow serializer test.
"""

from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import _render_flowlite, _title, serialize_for_ai


def test_render_flowlite_heading_carries_proxy_disclaimer():
    out = _render_flowlite({"volume_z": [], "put_call_delta": None, "unusual": []})
    assert out.startswith("## Flow proxy (volume-based — not fund-flow data)")


def test_render_flowlite_volume_z_line_includes_sigma_and_sign():
    payload = {
        "volume_z": [{"ticker": "SPY", "z": -2.3, "latest": 100, "avg": 50}],
        "put_call_delta": None,
        "unusual": [],
    }
    out = _render_flowlite(payload)
    assert "SPY -2.3σ" in out


def test_render_flowlite_volume_z_caps_at_eight_and_sorted_order_preserved():
    rows = [{"ticker": f"T{i}", "z": float(i), "latest": 1, "avg": 1} for i in range(12)]
    out = _render_flowlite({"volume_z": rows, "put_call_delta": None, "unusual": []})
    line = next(line for line in out.split("\n") if line.startswith("- Volume z"))
    assert line.count("σ") == 8


def test_render_flowlite_put_call_delta_line():
    payload = {
        "volume_z": [],
        "put_call_delta": {"ticker": "SPY", "latest": 1.25, "prior": 0.9, "delta": 0.35},
        "unusual": [],
    }
    out = _render_flowlite(payload)
    assert "- SPY P/C volume ratio 1.25 (Δ +0.35 vs prior chain)" in out


def test_render_flowlite_unusual_rows_use_describe_unusual():
    payload = {
        "volume_z": [],
        "put_call_delta": None,
        "unusual": [
            {
                "side": "call",
                "strike": "450.00",
                "expiry": "2026-10-16",
                "volume": 5000,
                "oi": 1000,
                "volume_ratio": 5.0,
                "iv_z": 2.1,
                "triggers": [],
                "score": 1.0,
            }
        ],
    }
    out = _render_flowlite(payload)
    assert "- Unusual: call 450.00 2026-10-16: vol/OI 5.0 — volume 5,000 vs OI 1,000" in out


def test_render_flowlite_empty_payload_honest_fallback():
    out = _render_flowlite({"volume_z": [], "put_call_delta": None, "unusual": []})
    assert "_(insufficient stored data — needs nightly bar ingest + a prior chain)_" in out


@pytest.mark.parametrize("payload", [{}, None, "nonsense"])
def test_render_flowlite_degenerate_payload_is_explicit_not_empty(payload):
    out = _render_flowlite(payload)
    assert out.startswith("## Flow proxy (volume-based — not fund-flow data)")
    assert "_(insufficient stored data — needs nightly bar ingest + a prior chain)_" in out


def test_flowlite_title():
    assert _title("flowlite") == "Flow proxy (volume-based)"


@pytest.mark.django_db
def test_done_flowlite_section_renders_markdown_in_full_flow():
    # Pins the _RENDERERS["flowlite"] registration: without it, _render_section
    # falls back to a raw ```json dict dump on every snapshot.
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["flowlite"], source="manual", status="ready")
    SnapshotSection.objects.create(
        snapshot=s,
        kind="flowlite",
        status="done",
        payload={
            "proxy_note": "volume-based flow proxy — not fund-flow data",
            "volume_z": [{"ticker": "SPY", "z": 2.4, "latest": 100, "avg": 40}],
            "put_call_delta": None,
            "unusual": [],
        },
    )
    out = serialize_for_ai(s)
    assert "## Flow proxy (volume-based — not fund-flow data)" in out
    assert "SPY +2.4σ" in out
    assert "```json" not in out


@pytest.mark.django_db
def test_failed_flowlite_section_renders_unavailable_with_proper_title():
    p = TradingProfile.objects.create(name="P", style="x")
    s = Snapshot.objects.create(profile=p, includes=["flowlite"], source="manual", status="ready")
    SnapshotSection.objects.create(
        snapshot=s, kind="flowlite", status="failed", payload={}, error="RuntimeError: x"
    )
    out = serialize_for_ai(s)
    assert "## Flow proxy (volume-based)" in out
    assert "unavailable" in out
