from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotSection
from apps.thesis.models import Thesis
from apps.threads.coach import assemble_coach_context, build_system_prompt

NOW = datetime(2026, 5, 29, 14, 30, tzinfo=UTC)


@pytest.mark.django_db
def test_system_prompt_wraps_style_and_includes_date_when_enabled():
    p = TradingProfile.objects.create(name="p", style="Aggressive intraday")
    out = build_system_prompt(p, now=NOW)
    assert "Aggressive intraday" in out
    assert "observational" in out.lower()
    assert "2026-05-29" in out


@pytest.mark.django_db
def test_system_prompt_is_legacy_style_only_when_disabled():
    p = TradingProfile.objects.create(name="p", style="Aggressive intraday", enable_coach=False)
    assert build_system_prompt(p, now=NOW) == "Aggressive intraday"


def test_system_prompt_none_profile_is_empty():
    assert build_system_prompt(None, now=NOW) == ""


@pytest.mark.django_db
def test_system_prompt_omits_style_header_when_style_is_blank():
    p = TradingProfile.objects.create(name="p", style="")
    out = build_system_prompt(p, now=NOW)
    assert "observational" in out.lower()
    assert "## Your trading style" not in out


@pytest.fixture
def coach_profile(db) -> TradingProfile:
    return TradingProfile.objects.create(name="c", style="s")


def _snap(profile, *, ticker="NVDA", last=188.2) -> Snapshot:
    snap = Snapshot.objects.create(
        profile=profile, status="ready", includes=["quotes"],
        source="manual", primary_ticker=ticker,
    )
    SnapshotSection.objects.create(
        snapshot=snap, kind="quotes", status="done", payload={ticker: {"last": last}}
    )
    return snap


@pytest.mark.django_db
def test_coach_empty_when_disabled(coach_profile):
    coach_profile.enable_coach = False
    coach_profile.save()
    assert assemble_coach_context(_snap(coach_profile), coach_profile) == ""


@pytest.mark.django_db
def test_coach_empty_without_primary_ticker(coach_profile):
    snap = Snapshot.objects.create(
        profile=coach_profile, status="ready", includes=["quotes"], source="manual"
    )
    assert snap.primary_ticker is None
    assert assemble_coach_context(snap, coach_profile) == ""


@pytest.mark.django_db
def test_coach_empty_when_no_history(coach_profile):
    # primary_ticker set, but no theses / no prior snapshot / no recall / no track record
    assert assemble_coach_context(_snap(coach_profile), coach_profile) == ""


@pytest.mark.django_db
def test_coach_includes_open_thesis_with_header(coach_profile):
    Thesis.objects.create(
        title="AI capex", ticker="NVDA", direction="bullish",
        conviction=4, status="open", target_price=210,
    )
    out = assemble_coach_context(_snap(coach_profile), coach_profile)
    assert "🧭 What you already know" in out
    assert "Open theses on NVDA" in out
    assert "AI capex" in out


@pytest.mark.django_db
def test_coach_includes_diff_vs_prior(coach_profile):
    prior = _snap(coach_profile, last=181.1)    # prior ready snapshot, same ticker
    # Pin captured_at strictly earlier — previous_snapshot_for uses captured_at__lt,
    # and two auto_now_add rows could otherwise collide on timestamp (flaky).
    Snapshot.objects.filter(pk=prior.pk).update(captured_at=timezone.now() - timedelta(hours=1))
    curr = _snap(coach_profile, last=188.2)
    out = assemble_coach_context(curr, coach_profile)
    assert "Since your last look" in out


@pytest.mark.django_db
def test_coach_caps_open_theses_at_three(coach_profile):
    for i in range(5):
        Thesis.objects.create(
            title=f"thesis-{i}", ticker="NVDA", direction="bullish",
            conviction=3, status="open",
        )
    out = assemble_coach_context(_snap(coach_profile), coach_profile)
    assert out.count("[bullish · conviction") == 3


@pytest.mark.django_db
def test_coach_never_raises_when_a_subsource_throws(coach_profile, monkeypatch):
    Thesis.objects.create(
        title="AI capex", ticker="NVDA", direction="bullish", conviction=4, status="open"
    )

    def boom(*a, **k):
        raise RuntimeError("recall is down")

    monkeypatch.setattr("apps.recall.services.search.related_to_ticker", boom)
    out = assemble_coach_context(_snap(coach_profile), coach_profile)  # must NOT raise
    assert "Open theses on NVDA" in out  # the healthy section still renders
