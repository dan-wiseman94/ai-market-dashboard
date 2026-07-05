"""Tests for the coverage revision service.

``run_structured`` has NO ``MOCK_EXTERNAL`` short-circuit, so every test patches
``apps.strategy.coverage.services.revise.run_structured`` (the name bound in the service
module) to return a ``CoverageRevisionDraft`` — the AI is never really called.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.ai.cost import CostCapExceededError
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.strategy.coverage.schemas import CoverageRevisionDraft
from apps.strategy.coverage.services.revise import revise_coverage
from apps.strategy.models import CoverageNote, CoverageRevision

PATCH_TARGET = "apps.strategy.coverage.services.revise.run_structured"


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="p", style="s", default_provider="claude")


@pytest.fixture
def provider_cfg(db) -> ProviderConfig:
    cfg = ProviderConfig.objects.create(
        provider="claude", enabled=True, default_model="claude-opus-4-8"
    )
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


@pytest.fixture
def snapshot(db, profile) -> Snapshot:
    snap = Snapshot.objects.create(
        profile=profile, status="ready", primary_ticker="SPY", source="manual"
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={"SPY": {"last": 525.0}}
    )
    return snap


def _draft(
    *, material_change=True, stance="bull", conviction=3, reason="r"
) -> CoverageRevisionDraft:
    return CoverageRevisionDraft(
        material_change=material_change,
        stance=stance,
        conviction=conviction,
        bull_case="upside",
        bear_case="downside",
        key_levels={"support": 520.0},
        watching_for="CPI print",
        reason=reason,
    )


def test_first_sight_creates_note_and_initial_revision(profile, provider_cfg, snapshot):
    assert not CoverageNote.objects.filter(ticker="SPY").exists()

    with patch(PATCH_TARGET, return_value=_draft(stance="bull", conviction=4)):
        rev = revise_coverage("spy", snapshot, profile=profile)  # lowercase → normalized

    note = CoverageNote.objects.get(ticker="SPY")
    assert note.stance == "bull"
    assert note.conviction == 4
    assert rev is not None
    assert rev.note_id == note.id
    assert rev.new["stance"] == "bull"
    assert rev.source_snapshot_id == snapshot.id
    assert CoverageRevision.objects.filter(note=note).count() == 1


def test_material_change_updates_note_and_records_revision(profile, provider_cfg, snapshot):
    note = CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=2, bull_case="old")

    with patch(
        PATCH_TARGET,
        return_value=_draft(material_change=True, stance="bear", conviction=4, reason="lost 520"),
    ):
        rev = revise_coverage("SPY", snapshot, profile=profile)

    note.refresh_from_db()
    assert note.stance == "bear"
    assert note.conviction == 4
    assert rev is not None
    assert rev.prior["stance"] == "bull"
    assert rev.new["stance"] == "bear"
    assert rev.reason == "lost 520"


def test_reaffirm_no_material_change_creates_no_revision(profile, provider_cfg, snapshot):
    note = CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=3, bull_case="x")
    before = CoverageRevision.objects.count()

    with patch(
        PATCH_TARGET,
        return_value=_draft(material_change=False, stance="bull", conviction=3),
    ):
        rev = revise_coverage("SPY", snapshot, profile=profile)

    assert rev is None
    assert CoverageRevision.objects.count() == before
    note.refresh_from_db()
    assert note.stance == "bull"  # untouched


def test_no_key_skips_without_calling_ai_or_creating_note(profile, snapshot):
    ProviderConfig.objects.create(provider="claude", enabled=True)  # no api_key set

    with patch(PATCH_TARGET) as run_structured:
        rev = revise_coverage("SPY", snapshot, profile=profile)

    run_structured.assert_not_called()
    assert rev is None
    assert not CoverageNote.objects.filter(ticker="SPY").exists()
    assert not CoverageRevision.objects.exists()


def test_cost_cap_exceeded_skips_without_calling_ai(profile, provider_cfg, snapshot):
    with (
        patch(
            "apps.strategy.coverage.services.revise.check_daily_cap",
            side_effect=CostCapExceededError("daily cap"),
        ),
        patch(PATCH_TARGET) as run_structured,
    ):
        rev = revise_coverage("SPY", snapshot, profile=profile)

    run_structured.assert_not_called()
    assert rev is None
    assert not CoverageNote.objects.filter(ticker="SPY").exists()


def test_ai_failure_is_best_effort_no_revision(profile, provider_cfg, snapshot):
    note = CoverageNote.objects.create(ticker="SPY", stance="bull", conviction=3)

    with patch(PATCH_TARGET, side_effect=RuntimeError("boom")):
        rev = revise_coverage("SPY", snapshot, profile=profile)  # must not raise

    assert rev is None
    note.refresh_from_db()
    assert note.stance == "bull"  # unchanged
    assert not CoverageRevision.objects.exists()
