from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.profiles.models import AgentPreset


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
    # 0008_seed_macro_fundamentals_preset
    "macro-fundamentals-brief",
}


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
        "structured": True,
    }
    resp = api.post("/api/presets/", payload, format="json")
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Custom Preset"
    assert body["slug"] == "custom-preset"
    assert body["structured"] is True
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
    resp = api.patch(
        f"/api/presets/{preset_b.id}/",
        {"slug": preset_a.slug},
        format="json",
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["code"] == "duplicate"


def test_structured_is_declared_as_metadata_not_a_switch():
    """`structured` records how the author describes the objective; nothing routes
    on it, because only `objective_template` travels into the composer. The Features
    registry must therefore exempt it explicitly rather than advertise a behaviour."""
    from apps.core.features import EXEMPT_MODEL_FIELDS, model_field_pairs

    assert "profiles.AgentPreset.structured" in EXEMPT_MODEL_FIELDS
    assert ("profiles.AgentPreset", "structured") not in model_field_pairs()
