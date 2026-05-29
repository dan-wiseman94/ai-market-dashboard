from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.snapshots.serializer import serialize_for_ai


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s")


@pytest.mark.django_db
def test_serialize_renders_intel_section(profile):
    snap = Snapshot.objects.create(
        profile=profile,
        status="ready",
        includes=["breadth"],
        source="manual",
        primary_ticker="NVDA",
    )
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="breadth",
        status="done",
        payload={"spx_last": 1, "qqq_last": 1, "vix_last": 1, "sectors": {}, "breadth": {}},
    )
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="intel",
        status="done",
        payload={
            "rotation": {
                "ranked": [
                    {"etf": "XLK", "sector": "Technology", "pct": 1.8},
                    {"etf": "XLE", "sector": "Energy", "pct": -1.2},
                ]
            },
            "relative_strength": {
                "ticker": "NVDA",
                "benchmark": "SPY",
                "windows": [{"days": 5, "ticker_pct": 3.9, "benchmark_pct": 1.2, "rs_pct": 2.7}],
            },
            "iv": {
                "ticker": "NVDA",
                "atm_iv": 0.54,
                "mean_30d": 0.48,
                "z": 1.2,
                "percentile": 0.85,
                "skew": 0.03,
                "term": {
                    "front": "2026-06-05",
                    "front_iv": 0.54,
                    "next": "2026-06-12",
                    "next_iv": 0.49,
                    "shape": "backwardation",
                },
            },
        },
    )
    out = serialize_for_ai(snap)
    assert "## Market intelligence" in out
    assert "XLK" in out and "Technology" in out
    assert "relative strength vs SPY" in out.lower() or "RS" in out
    assert "NVDA" in out and "54" in out
    assert "backwardation" in out


@pytest.mark.django_db
def test_serialize_without_intel_is_unchanged(profile):
    snap = Snapshot.objects.create(
        profile=profile, status="ready", includes=["breadth"], source="manual"
    )
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="breadth",
        status="done",
        payload={"spx_last": 1, "qqq_last": 1, "vix_last": 1, "sectors": {}, "breadth": {}},
    )
    assert "## Market intelligence" not in serialize_for_ai(snap)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bad_payload",
    [
        {"rotation": {"ranked": ["notadict", None, 42]}},
        {"rotation": {"ranked": "notalist"}},
        {"rotation": "notadict"},
        {"relative_strength": {"windows": ["x", None]}},
        {"iv": {"atm_iv": 0.5, "term": "notadict"}},
        {"iv": "notadict"},
    ],
)
def test_serialize_never_raises_on_malformed_intel(profile, bad_payload):
    snap = Snapshot.objects.create(
        profile=profile,
        status="ready",
        includes=["breadth"],
        source="manual",
        primary_ticker="NVDA",
    )
    SnapshotSection.objects.create(snapshot=snap, kind="intel", status="done", payload=bad_payload)
    out = serialize_for_ai(snap)  # must NOT raise
    assert isinstance(out, str)


@pytest.mark.django_db
def test_serialize_tolerates_malformed_intel_payload(profile):
    snap = Snapshot.objects.create(
        profile=profile,
        status="ready",
        includes=["breadth"],
        source="manual",
        primary_ticker="NVDA",
    )
    SnapshotSection.objects.create(
        snapshot=snap,
        kind="intel",
        status="done",
        payload={
            "rotation": {"ranked": [{"sector": "Technology", "pct": 1.0}]},  # missing "etf"
            "iv": {
                "ticker": "NVDA",
                "atm_iv": 0.5,
                "term": {"front_iv": 0.5, "next_iv": 0.4},
            },  # term missing "shape"
        },
    )
    out = serialize_for_ai(snap)  # must NOT raise
    assert "## Market intelligence" in out
    assert "→ None" not in out
