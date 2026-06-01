"""Tests for GET /api/dashboard/ — command-centre aggregator."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.briefing.models import BriefingRun
from apps.observer.models import ObserverSchedule
from apps.profiles.models import TradingProfile
from apps.thesis.models import Thesis
from apps.triggers.models import EventTrigger, TriggerFiring


@pytest.fixture
def api():
    return APIClient()


# ---------------------------------------------------------------------------
# 1. Empty DB → 200 with all five keys present
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_empty_db_returns_200_with_all_keys(api):
    r = api.get("/api/dashboard/")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"theses", "events", "observer", "triggers", "briefing"}
    # sane empty defaults
    assert isinstance(body["theses"], list)
    assert isinstance(body["events"], dict)
    assert isinstance(body["observer"], dict)
    assert isinstance(body["triggers"], dict)
    # briefing is null when no run exists
    assert body["briefing"] is None


# ---------------------------------------------------------------------------
# 2. Seed data — theses, triggers, briefing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_with_seed_data(api):
    # Open thesis
    Thesis.objects.create(
        title="Long NVDA",
        ticker="NVDA",
        direction="bullish",
        target_price=Decimal("150"),
        invalidation_price=Decimal("90"),
        status="open",
    )

    # Enabled trigger + one firing
    prof = TradingProfile.objects.create(name="p", style="s")
    trigger = EventTrigger.objects.create(
        profile=prof,
        name="test-trigger",
        condition={"all": []},
        enabled=True,
    )
    TriggerFiring.objects.create(trigger=trigger, matched_values={"price": 100})

    # BriefingRun with data containing a summary-style theses list
    BriefingRun.objects.create(status="ready", data={"theses": [{"ticker": "NVDA"}]})

    with patch(
        "apps.briefing.services.assemble.fetch_quotes",
        return_value={"NVDA": {"last": 120.0}},
    ):
        r = api.get("/api/dashboard/")

    assert r.status_code == 200
    body = r.json()

    # theses: open thesis reflected with ticker
    assert any(t["ticker"] == "NVDA" for t in body["theses"])
    nvda = next(t for t in body["theses"] if t["ticker"] == "NVDA")
    assert nvda["direction"] == "bullish"
    assert nvda["current"] == 120.0

    # triggers: at least one armed trigger and one firing entry
    trig_section = body["triggers"]
    assert trig_section["armed_count"] >= 1
    assert len(trig_section["latest_firings"]) >= 1
    first_firing = trig_section["latest_firings"][0]
    assert first_firing["trigger_id"] == trigger.id
    assert "fired_at" in first_firing

    # briefing: latest BriefingRun's status
    assert body["briefing"] is not None
    assert body["briefing"]["status"] == "ready"


@pytest.mark.django_db
def test_observer_section_counts_enabled_schedules(api):
    prof = TradingProfile.objects.create(name="p2", style="s")
    ObserverSchedule.objects.create(name="morning", profile=prof, enabled=True)
    ObserverSchedule.objects.create(name="evening", profile=prof, enabled=False)

    r = api.get("/api/dashboard/")
    assert r.status_code == 200
    obs = r.json()["observer"]
    assert obs["enabled_schedules"] == 1


# ---------------------------------------------------------------------------
# 3. Never-raise: a section that raises is swallowed → endpoint still 200
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_never_raise_swallows_section_error(api):
    """Monkeypatch _theses_section to raise; endpoint must survive with theses=[] default."""
    with patch(
        "apps.dashboard.views._theses_section",
        side_effect=RuntimeError("db on fire"),
    ):
        r = api.get("/api/dashboard/")

    assert r.status_code == 200
    body = r.json()
    # All five keys still present
    assert set(body.keys()) >= {"theses", "events", "observer", "triggers", "briefing"}
    # The failing section degrades to its empty default
    assert body["theses"] == []


@pytest.mark.django_db
def test_never_raise_swallows_observer_error(api):
    """Monkeypatch _observer_summary to raise; the observer default must match the frontend
    DashboardObserver contract (not a bare {}) so the SPA renders empty instead of crashing."""
    with patch(
        "apps.dashboard.views._observer_summary",
        side_effect=RuntimeError("observer exploded"),
    ):
        r = api.get("/api/dashboard/")

    assert r.status_code == 200
    assert r.json()["observer"] == {"enabled_schedules": 0, "runs_today": 0}


@pytest.mark.django_db
def test_never_raise_swallows_triggers_error(api):
    """Monkeypatch _triggers_summary to raise; endpoint still 200 and the triggers default
    matches the frontend DashboardTriggers contract (was a bare {} that crashed the SPA)."""
    with patch(
        "apps.dashboard.views._triggers_summary",
        side_effect=RuntimeError("triggers exploded"),
    ):
        r = api.get("/api/dashboard/")

    assert r.status_code == 200
    body = r.json()
    assert body["triggers"] == {"armed_count": 0, "latest_firings": []}
