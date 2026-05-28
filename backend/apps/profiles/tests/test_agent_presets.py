from __future__ import annotations

import pytest
from django.db import IntegrityError
from rest_framework.test import APIClient

from apps.profiles.models import AgentPreset

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def api():
    return APIClient()


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_slug_auto_generated_from_name():
    preset = AgentPreset.objects.create(
        name="My Cool Preset",
        objective_template="Do something useful.",
    )
    assert preset.slug == "my-cool-preset"


@pytest.mark.django_db
def test_explicit_slug_preserved():
    preset = AgentPreset.objects.create(
        name="Some Preset",
        slug="custom-slug",
        objective_template="Some objective.",
    )
    assert preset.slug == "custom-slug"


@pytest.mark.django_db
def test_defaults():
    preset = AgentPreset.objects.create(
        name="Defaults Test",
        objective_template="Check defaults.",
    )
    assert preset.structured is False
    assert preset.builtin is False
    assert preset.active is True
    assert preset.default_includes == []
    assert preset.description == ""


@pytest.mark.django_db
def test_slug_uniqueness_raises():
    AgentPreset.objects.create(
        name="First",
        slug="same-slug",
        objective_template="First preset.",
    )
    with pytest.raises(IntegrityError):
        AgentPreset.objects.create(
            name="Second",
            slug="same-slug",
            objective_template="Second preset.",
        )


@pytest.mark.django_db
def test_str():
    preset = AgentPreset(name="My Preset", slug="my-preset", objective_template="x")
    assert str(preset) == "My Preset"


# ---------------------------------------------------------------------------
# Seed migration tests
# ---------------------------------------------------------------------------

# Builtin presets seeded by the data migrations. Keep in sync when a new seed
# migration lands (0005 seeds the first four, 0006 the next eight).
EXPECTED_BUILTIN_SLUGS = {
    # 0005_seed_agent_presets
    "earnings-prep",
    "devils-advocate",
    "pre-trade-bias-check",
    "triage-pass",
    # 0006_seed_more_agent_presets
    "morning-gameplan",
    "closing-wrap",
    "risk-audit",
    "income-setup",
    "macro-read",
    "catalyst-scan",
    "breakout-scan",
    "trade-postmortem",
}

EXPECTED_INCLUDES: dict[str, list[str]] = {
    # 0005_seed_agent_presets
    "earnings-prep": ["quotes", "ohlc", "news", "chain"],
    "devils-advocate": ["quotes", "positions", "ohlc"],
    "pre-trade-bias-check": ["quotes", "ohlc", "breadth"],
    "triage-pass": ["quotes", "positions", "breadth", "news"],
    # 0006_seed_more_agent_presets
    "morning-gameplan": ["quotes", "ohlc", "news", "events", "breadth"],
    "closing-wrap": ["quotes", "positions", "ohlc", "news"],
    "risk-audit": ["quotes", "positions", "breadth"],
    "income-setup": ["quotes", "ohlc", "chain"],
    "macro-read": ["breadth", "events", "news"],
    "catalyst-scan": ["news", "events", "quotes"],
    "breakout-scan": ["quotes", "ohlc", "breadth"],
    "trade-postmortem": ["quotes", "ohlc", "news"],
}


@pytest.mark.django_db
def test_seed_migration_creates_builtins():
    builtins = AgentPreset.objects.filter(builtin=True)
    slugs = set(builtins.values_list("slug", flat=True))
    assert slugs == EXPECTED_BUILTIN_SLUGS


@pytest.mark.django_db
def test_seed_migration_includes_correct():
    for slug, expected_includes in EXPECTED_INCLUDES.items():
        preset = AgentPreset.objects.get(slug=slug)
        assert preset.default_includes == expected_includes, (
            f"{slug}: expected {expected_includes}, got {preset.default_includes}"
        )


@pytest.mark.django_db
def test_seed_migration_builtins_are_active():
    for slug in EXPECTED_BUILTIN_SLUGS:
        preset = AgentPreset.objects.get(slug=slug)
        assert preset.active is True


# ---------------------------------------------------------------------------
# API CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_presets_includes_builtins(api):
    resp = api.get("/api/presets/")
    assert resp.status_code == 200
    data = resp.json()
    slugs = {p["slug"] for p in data}
    assert EXPECTED_BUILTIN_SLUGS.issubset(slugs)


@pytest.mark.django_db
def test_create_custom_preset(api):
    payload = {
        "name": "Custom Preset",
        "objective_template": "Do something custom.",
        "default_includes": ["quotes", "ohlc"],
        "structured": True,
    }
    resp = api.post("/api/presets/", payload, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Custom Preset"
    assert body["slug"] == "custom-preset"
    assert body["structured"] is True
    assert body["default_includes"] == ["quotes", "ohlc"]
    # Client must NOT be able to forge builtin=True
    assert body["builtin"] is False


@pytest.mark.django_db
def test_create_preset_builtin_forced_false(api):
    """Even if client sends builtin=true, the server must ignore it."""
    payload = {
        "name": "Sneaky Preset",
        "objective_template": "Try to set builtin.",
        "builtin": True,
    }
    resp = api.post("/api/presets/", payload, format="json")
    assert resp.status_code == 201
    assert resp.json()["builtin"] is False


@pytest.mark.django_db
def test_patch_preset(api):
    preset = AgentPreset.objects.create(
        name="Editable",
        objective_template="Original objective.",
        default_includes=["quotes"],
    )
    resp = api.patch(
        f"/api/presets/{preset.id}/",
        {"objective_template": "Updated objective.", "default_includes": ["quotes", "news"]},
        format="json",
    )
    assert resp.status_code == 200
    preset.refresh_from_db()
    assert preset.objective_template == "Updated objective."
    assert preset.default_includes == ["quotes", "news"]


@pytest.mark.django_db
def test_delete_preset(api):
    preset = AgentPreset.objects.create(
        name="To Delete",
        objective_template="Gone soon.",
    )
    resp = api.delete(f"/api/presets/{preset.id}/")
    assert resp.status_code == 204
    assert not AgentPreset.objects.filter(id=preset.id).exists()


@pytest.mark.django_db
def test_retrieve_single_preset(api):
    preset = AgentPreset.objects.get(slug="earnings-prep")
    resp = api.get(f"/api/presets/{preset.id}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "earnings-prep"
    assert body["builtin"] is True
    assert "objective_template" in body
    assert "default_includes" in body


@pytest.mark.django_db
def test_create_duplicate_name_returns_400(api):
    """Two POSTs with the same name slugify to the same slug; second must be 400, not 500."""
    payload = {"name": "Clash Preset", "objective_template": "First one."}
    resp1 = api.post("/api/presets/", payload, format="json")
    assert resp1.status_code == 201

    resp2 = api.post("/api/presets/", payload, format="json")
    assert resp2.status_code == 400
    body = resp2.json()
    assert body["code"] == "duplicate"


@pytest.mark.django_db
def test_patch_slug_collision_returns_400(api):
    """PATCHing a preset's slug to collide with an existing slug must return 400, not 500."""
    preset_a = AgentPreset.objects.create(
        name="Alpha Preset",
        objective_template="Alpha.",
    )
    preset_b = AgentPreset.objects.create(
        name="Beta Preset",
        objective_template="Beta.",
    )
    # Explicitly set preset_b's slug to match preset_a's
    resp = api.patch(
        f"/api/presets/{preset_b.id}/",
        {"slug": preset_a.slug},
        format="json",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "duplicate"
