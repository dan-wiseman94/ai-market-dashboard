"""SystemSettings: UI-editable runtime knobs that override env/settings defaults."""

import json

import pytest
from django.test import Client, override_settings

from apps.core.models import SystemSettings
from apps.core.runtime_config import runtime_config


@pytest.mark.django_db
@override_settings(AI_RETENTION_OHLC_DAYS=400, AI_FAILOVER_ENABLED=False)
def test_runtime_config_falls_back_to_settings_when_unset():
    rc = runtime_config()
    assert rc.retention_ohlc_days == 400
    assert rc.ai_failover_enabled is False


@pytest.mark.django_db
@override_settings(AI_RETENTION_OHLC_DAYS=400)
def test_runtime_config_prefers_db_override():
    cfg = SystemSettings.load()
    cfg.retention_ohlc_days = 30
    cfg.ai_failover_enabled = True
    cfg.save()
    rc = runtime_config()
    assert rc.retention_ohlc_days == 30
    assert rc.ai_failover_enabled is True


@pytest.mark.django_db
@override_settings(AIEVAL_SCHEDULED_PROVIDER="claude")
def test_aieval_provider_defaults_to_setting_and_accepts_an_override():
    assert runtime_config().aieval_scheduled_provider == "claude"
    r = Client().patch(
        "/api/settings/",
        data=json.dumps({"aieval_scheduled_provider": "openai"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.json()["aieval_scheduled_provider"] == "openai"
    assert runtime_config().aieval_scheduled_provider == "openai"


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["aieval_scheduled_provider", "ai_failover_provider"])
def test_provider_knobs_reject_an_unknown_provider(key):
    """A free-text provider name silently disables the knob — reject it at write time."""
    c = Client()
    bad = c.patch(
        "/api/settings/", data=json.dumps({key: "bogus"}), content_type="application/json"
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "invalid_value"
    blank = c.patch("/api/settings/", data=json.dumps({key: ""}), content_type="application/json")
    assert blank.status_code == 200


@pytest.mark.django_db
@override_settings(AI_FAILOVER_ENABLED=True)
def test_null_field_inherits_even_when_setting_is_truthy():
    # A SystemSettings row exists but the field is NULL → still inherits the setting.
    SystemSettings.load()
    assert runtime_config().ai_failover_enabled is True


@pytest.mark.django_db
@override_settings(OBSERVER_RESPONSE_CACHE_TTL_SECONDS=1800)
def test_observer_cache_ttl_reflects_db_override():
    cfg = SystemSettings.load()
    cfg.observer_response_cache_ttl_seconds = 600
    cfg.save()
    assert runtime_config().observer_response_cache_ttl_seconds == 600


@pytest.mark.django_db
@override_settings(AI_RETENTION_OHLC_DAYS=400)
def test_get_returns_resolved_effective_values():
    response = Client().get("/api/settings/")
    assert response.status_code == 200
    body = response.json()
    assert body["retention_ohlc_days"] == 400
    assert "aieval_scheduled_model" in body


@pytest.mark.django_db
def test_patch_persists_overrides_and_returns_resolved():
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"retention_ohlc_days": 200, "ai_failover_enabled": True}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["retention_ohlc_days"] == 200
    assert response.json()["ai_failover_enabled"] is True
    cfg = SystemSettings.load()
    assert cfg.retention_ohlc_days == 200


@pytest.mark.django_db
def test_patch_rejects_unknown_field():
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"nope": 1}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "unknown_field"


@pytest.mark.django_db
def test_patch_rejects_zero_retention():
    # 0 days would make the next prune delete every row of that model.
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"retention_chain_days": 0}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_value"
    # null still allowed (disables pruning, inherits default)
    ok = Client().patch(
        "/api/settings/",
        data=json.dumps({"retention_chain_days": None}),
        content_type="application/json",
    )
    assert ok.status_code == 200


@pytest.mark.django_db
def test_patch_rejects_ohlc_retention_below_postmortem_horizon():
    # Post-mortems resolve against OHLC by date up to the 90d horizon; a low OHLC
    # retention would prune the bars they need.
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"retention_ohlc_days": 30}),
        content_type="application/json",
    )
    assert response.status_code == 400
    ok = Client().patch(
        "/api/settings/",
        data=json.dumps({"retention_ohlc_days": 120}),
        content_type="application/json",
    )
    assert ok.status_code == 200
    assert ok.json()["retention_ohlc_days"] == 120


@pytest.mark.django_db
def test_patch_rejects_negative_number():
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"retention_ohlc_days": -5}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_value"


@pytest.mark.django_db
@override_settings(TRADINGVIEW_TOOLS_ENABLED=False)
def test_tradingview_tools_enabled_inherits_then_overrides():
    assert runtime_config().tradingview_tools_enabled is False
    cfg = SystemSettings.load()
    cfg.tradingview_tools_enabled = True
    cfg.save()
    assert runtime_config().tradingview_tools_enabled is True


@pytest.mark.django_db
def test_patch_accepts_tradingview_tools_enabled():
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"tradingview_tools_enabled": True}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["tradingview_tools_enabled"] is True
    assert SystemSettings.load().tradingview_tools_enabled is True
