"""GET /api/features/ — the contract the Features page renders from."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from django.test import Client, override_settings

from apps.core.features import FEATURES
from apps.core.models import SystemSettings


def _get() -> dict:
    response = Client().get("/api/features/")
    assert response.status_code == 200
    return response.json()


def _rows(body: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for bucket in ("toggles", "numbers", "texts", "per_object"):
        for row in body[bucket]:
            out[row["key"]] = row
    return out


@pytest.mark.django_db
def test_every_registry_row_appears_exactly_once():
    body = _get()
    seen = [r["key"] for b in ("toggles", "numbers", "texts", "per_object") for r in body[b]]
    assert sorted(seen) == sorted(f.key for f in FEATURES)
    assert len(seen) == len(set(seen)), "a row was emitted into two buckets"


@pytest.mark.django_db
def test_groups_are_ordered_and_cover_every_row():
    body = _get()
    orders = [g["order"] for g in body["groups"]]
    assert orders == sorted(orders)
    group_keys = {g["key"] for g in body["groups"]}
    assert {r["group"] for r in _rows(body).values()} <= group_keys


@pytest.mark.django_db
def test_rows_carry_the_copy_the_page_renders():
    row = _rows(_get())["ai.failover"]
    assert row["label"] and row["summary"] and row["help"]
    assert row["editable"] is True
    assert row["write_path"] == "/api/settings/"
    assert row["field"] == "ai_failover_enabled"


@pytest.mark.django_db
@override_settings(AI_FAILOVER_ENABLED=True)
def test_source_is_default_when_nothing_overrides_it():
    row = _rows(_get())["ai.failover"]
    assert row["source"] == "default"
    assert row["override"] is None
    assert row["value"] is True


@pytest.mark.django_db
@override_settings(AI_FAILOVER_ENABLED=True)
def test_source_is_override_when_the_column_holds_a_value():
    cfg = SystemSettings.load()
    cfg.ai_failover_enabled = False
    cfg.save()
    row = _rows(_get())["ai.failover"]
    assert row["source"] == "override"
    assert row["override"] is False
    assert row["value"] is False
    # default_value is what "reset to default" restores — not the current value.
    assert row["default_value"] is True


@pytest.mark.django_db
def test_source_is_env_when_the_environment_names_the_variable():
    # override_settings does not touch os.environ, which is exactly what `source`
    # reads: presence in the process environment, never the value itself.
    with patch.dict(os.environ, {"AI_FAILOVER_ENABLED": "true"}):
        row = _rows(_get())["ai.failover"]
    assert row["source"] == "env"


@pytest.mark.django_db
def test_env_only_rows_are_read_only_and_explain_themselves():
    rows = _rows(_get())
    for key in (
        "ai.provider_max_retries",
        "ai.provider_timeout_seconds",
        "triggers.tick_seconds",
        "observer.beat_timezone",
    ):
        row = rows[key]
        assert row["editable"] is False, key
        assert row["write_path"] == "", key
        assert row["env_only_reason"], key
        assert row["env_var"], key


@pytest.mark.django_db
def test_numbers_carry_their_bounds_and_unit():
    row = _rows(_get())["spend.autonomous_daily_cap_usd"]
    assert row["is_float"] is True
    assert row["unit"] == "USD"
    assert row["min_value"] == 0


@pytest.mark.django_db
def test_choice_rows_carry_their_choices():
    row = _rows(_get())["ai.failover_provider"]
    assert {c["value"] for c in row["choices"]} == {"", "claude", "openai", "local"}
    assert row["max_length"] == 32


@pytest.mark.django_db
def test_per_object_rollup_counts_real_rows():
    from apps.profiles.models import TradingProfile

    TradingProfile.objects.create(name="A", style="s", enable_tools=True)
    TradingProfile.objects.create(name="B", style="s", enable_tools=False)
    row = _rows(_get())["profile.enable_tools"]
    assert row["on"] == 1
    assert row["total"] == 2
    assert row["degraded"] is False
    assert row["noun"] == "profiles"
    assert row["editable"] is False, "a per-object row must never render a global switch"
    assert row["deep_link"] == "/profiles"


@pytest.mark.django_db
def test_non_boolean_per_object_rows_report_no_on_count():
    from apps.profiles.models import TradingProfile

    TradingProfile.objects.create(name="A", style="s")
    row = _rows(_get())["profile.effort"]
    assert row["on"] is None, "'how many are on' is meaningless for a choice field"
    assert row["total"] == 1


@pytest.mark.django_db
def test_snapshot_section_rollup_reads_profile_includes():
    from apps.profiles.models import TradingProfile

    TradingProfile.objects.create(name="A", style="s", default_includes=["quotes", "news"])
    TradingProfile.objects.create(name="B", style="s", default_includes=["quotes"])
    rows = _rows(_get())
    assert rows["section.quotes"]["on"] == 2
    assert rows["section.news"]["on"] == 1
    assert rows["section.fed"]["on"] == 0


@pytest.mark.django_db
def test_vix_is_always_on_and_not_switchable():
    row = _rows(_get())["section.vix"]
    assert row["value"] is True
    assert row["editable"] is False
    assert row["env_only_reason"]


@pytest.mark.django_db
def test_a_failed_rollup_degrades_to_a_full_shape_not_a_zero_count():
    with patch("apps.core.feature_views._aggregate", side_effect=RuntimeError("db exploded")):
        row = _rows(_get())["profile.enable_tools"]
    assert row["degraded"] is True
    assert row["on"] is None and row["total"] is None, (
        "0 of 0 would render as a confident lie the user would act on"
    )


@pytest.mark.django_db
def test_a_failed_connection_probe_degrades_to_unknown_not_disconnected():
    with patch(
        "apps.market.services.tradingview.is_connected", side_effect=RuntimeError("redis down")
    ):
        row = _rows(_get())["ai.tradingview_tools"]
    assert row["requirement"]["satisfied"] is None
    assert row["requirement"]["manage_path"] == "/settings/connections"


@pytest.mark.django_db
def test_rows_without_a_connection_requirement_carry_none():
    assert _rows(_get())["ai.failover"]["requirement"] is None


@pytest.mark.django_db
def test_briefing_singleton_rows_write_to_the_briefing_endpoint():
    from apps.observer.models import BriefingConfig

    cfg = BriefingConfig.load()
    cfg.synthesis_enabled = False
    cfg.save()
    row = _rows(_get())["briefing.synthesis_enabled"]
    assert row["editable"] is True
    assert row["write_path"] == "/api/briefings/config/"
    assert row["field"] == "synthesis_enabled"
    assert row["value"] is False
    assert row["source"] == "override", "differs from the shipped default"
    assert row["costs_money"] is True and row["cost_note"]


@pytest.mark.django_db
def test_money_and_retroactive_flags_reach_the_payload():
    rows = _rows(_get())
    assert rows["strategy.anomaly_sweep"]["costs_money"] is True
    assert rows["methodology.returns_adjust_dividends"]["retroactive"] is True


@pytest.mark.django_db
def test_query_budget(django_assert_max_num_queries):
    """One aggregate per gated model plus the singleton reads — never per row.

    The singletons are created first so this measures the steady state: a first-ever
    ``get_or_create`` costs a savepoint + INSERT that has nothing to do with the
    endpoint's shape.
    """
    from apps.observer.models import BriefingConfig

    SystemSettings.load()
    BriefingConfig.load()
    with django_assert_max_num_queries(12):
        Client().get("/api/features/")
