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


def test_runtime_config_dataclass_covers_every_spec_field():
    """RuntimeConfig(**resolved) is built from _SPEC, so a field added to _SPEC without
    an annotation here raises TypeError on EVERY runtime_config() call — i.e. on every
    request and every task run, not just the one that reads the new knob."""
    from apps.core.runtime_config import _SPEC, RuntimeConfig

    assert set(RuntimeConfig.__dataclass_fields__) == {field for field, _, _ in _SPEC}


def test_every_spec_field_has_a_systemsettings_column():
    """The UI writes overrides by field name, so a _SPEC row with no column would
    accept a PATCH and then fail to persist it."""
    from apps.core.runtime_config import _SPEC

    columns = {f.name for f in SystemSettings._meta.get_fields()}
    assert {field for field, _, _ in _SPEC} <= columns


def test_editable_dollar_cap_is_float_typed():
    """type(default) is the coercer: an int default would truncate a fractional cap."""
    from apps.core.runtime_config import EDITABLE_FIELDS

    assert EDITABLE_FIELDS["ai_autonomous_daily_cap_usd"] is float


@pytest.mark.django_db
def test_patch_accepts_a_fractional_dollar_cap():
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"ai_autonomous_daily_cap_usd": 2.5}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["ai_autonomous_daily_cap_usd"] == 2.5
    assert SystemSettings.load().ai_autonomous_daily_cap_usd == 2.5


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("key", "max_length"),
    [("ai_failover_provider", 32), ("aieval_scheduled_model", 100)],
)
def test_patch_rejects_string_longer_than_the_column(key, max_length):
    # Without the length check this reaches Postgres and raises DataError — a 500.
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({key: "x" * (max_length + 1)}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_value"
    # The length check runs before the choices check, so a choice-bounded column still
    # reports the real reason rather than listing every allowed provider.
    assert f"at most {max_length} characters" in response.json()["message"]


@pytest.mark.django_db
def test_patch_accepts_a_string_that_exactly_fills_a_choiceless_column():
    # The boundary must pass — the length check rejects longer-than, not equal-to.
    ok = Client().patch(
        "/api/settings/",
        data=json.dumps({"aieval_scheduled_model": "x" * 100}),
        content_type="application/json",
    )
    assert ok.status_code == 200
    assert SystemSettings.load().aieval_scheduled_model == "x" * 100


def test_failover_provider_column_declares_the_registry_choices():
    # The Features page renders the dropdown from apps.core.features, but the API edge
    # enforces the column's OWN choices (views._check_column_limits). Let the two drift
    # and the page offers an option the API rejects, or the API accepts one the page
    # never shows.
    from apps.core.features import FEATURES

    registry = next(f for f in FEATURES if f.settings_field == "ai_failover_provider")
    field = SystemSettings._meta.get_field("ai_failover_provider")
    assert [c[0] for c in field.choices] == [c[0] for c in registry.choices]
    assert field.max_length == registry.max_length


@pytest.mark.django_db
@pytest.mark.parametrize("bad_value", ["gemini", "Claude", "openai "])
def test_patch_rejects_a_provider_outside_the_columns_choices(bad_value):
    # Without the column's choices any string up to 32 chars saved fine and the
    # failover lookup then silently found no ProviderConfig row — failover off, no error.
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"ai_failover_provider": bad_value}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_value"
    assert "claude" in response.json()["message"]
    assert SystemSettings.load().ai_failover_provider is None


@pytest.mark.django_db
@pytest.mark.parametrize("good_value", ["", "claude", "openai", "local"])
def test_patch_accepts_every_declared_provider_choice(good_value):
    # "" is a real choice — an explicit "no secondary", distinct from null (inherit).
    response = Client().patch(
        "/api/settings/",
        data=json.dumps({"ai_failover_provider": good_value}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["ai_failover_provider"] == good_value
    assert SystemSettings.load().ai_failover_provider == good_value


@pytest.mark.django_db
@override_settings(ANOMALY_SWEEP_ENABLED=True, RESTORE_FROM_UI_ENABLED=True)
def test_new_boolean_knobs_inherit_then_override():
    rc = runtime_config()
    assert rc.anomaly_sweep_enabled is True
    assert rc.restore_from_ui_enabled is True

    cfg = SystemSettings.load()
    cfg.anomaly_sweep_enabled = False
    cfg.restore_from_ui_enabled = False
    cfg.save()

    rc = runtime_config()
    assert rc.anomaly_sweep_enabled is False
    assert rc.restore_from_ui_enabled is False
