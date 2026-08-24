"""Tests for GET /api/dashboard/ — command-centre aggregator."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.observer.models import BriefingRun, EventTrigger, ObserverSchedule, TriggerFiring
from apps.profiles.models import TradingProfile
from apps.thesis.models import Thesis


@pytest.mark.django_db
def test_empty_db_returns_200_with_all_keys(api):
    r = api.get("/api/dashboard/")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"theses", "events", "observer", "triggers", "briefing"}
    assert isinstance(body["theses"], list)
    assert isinstance(body["events"], dict)
    assert isinstance(body["observer"], dict)
    assert isinstance(body["triggers"], dict)
    assert body["briefing"] is None


@pytest.mark.django_db
def test_with_seed_data(api):
    Thesis.objects.create(
        title="Long NVDA",
        ticker="NVDA",
        direction="bullish",
        target_price=Decimal("150"),
        invalidation_price=Decimal("90"),
        status="open",
    )

    prof = TradingProfile.objects.create(name="p", style="s")
    trigger = EventTrigger.objects.create(
        profile=prof,
        name="test-trigger",
        condition={"all": []},
        enabled=True,
    )
    TriggerFiring.objects.create(trigger=trigger, matched_values={"price": 100})

    BriefingRun.objects.create(status="ready", data={"theses": [{"ticker": "NVDA"}]})

    with patch(
        "apps.observer.briefing.services.assemble.fetch_quotes",
        return_value={"NVDA": {"last": 120.0}},
    ):
        r = api.get("/api/dashboard/")

    assert r.status_code == 200
    body = r.json()

    assert any(t["ticker"] == "NVDA" for t in body["theses"])
    nvda = next(t for t in body["theses"] if t["ticker"] == "NVDA")
    assert nvda["direction"] == "bullish"
    assert nvda["current"] == 120.0

    trig_section = body["triggers"]
    assert trig_section["armed_count"] >= 1
    assert len(trig_section["latest_firings"]) >= 1
    first_firing = trig_section["latest_firings"][0]
    assert first_firing["trigger_id"] == trigger.id
    assert "fired_at" in first_firing

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


@pytest.mark.django_db
def test_never_raise_swallows_section_error(api):
    """Monkeypatch _theses_section to raise; endpoint must survive with theses=[] default."""
    with patch(
        "apps.analytics.dashboard._theses_section",
        side_effect=RuntimeError("db on fire"),
    ):
        r = api.get("/api/dashboard/")

    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"theses", "events", "observer", "triggers", "briefing"}
    assert body["theses"] == []


@pytest.mark.django_db
def test_never_raise_swallows_observer_error(api):
    """Monkeypatch _observer_summary to raise; the observer default must match the frontend
    DashboardObserver contract (not a bare {}) so the SPA renders empty instead of crashing."""
    with patch(
        "apps.analytics.dashboard._observer_summary",
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
        "apps.analytics.dashboard._triggers_summary",
        side_effect=RuntimeError("triggers exploded"),
    ):
        r = api.get("/api/dashboard/")

    assert r.status_code == 200
    body = r.json()
    assert body["triggers"] == {"armed_count": 0, "latest_firings": []}
