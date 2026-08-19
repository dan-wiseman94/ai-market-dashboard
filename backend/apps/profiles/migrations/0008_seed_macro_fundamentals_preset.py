from __future__ import annotations

from django.db import migrations

BUILTINS = [
    {
        "slug": "macro-fundamentals-brief",
        "name": "Macro & fundamentals brief",
        "description": "Macro regime (FRED + Treasury) tied to per-name fundamentals and SEC filings.",
        "objective_template": (
            "Frame today through the macro lens and the fundamentals. Start with the macro "
            "backdrop — the key FRED indicators (CPI, unemployment, fed funds, the Treasury yield "
            "curve) and what they imply for rates and risk appetite — then for each watchlist name "
            "connect that regime to the company's fundamentals and any recent SEC filings "
            "(10-K/10-Q/8-K, insider Form 4 activity). Conclude with which names look best and worst "
            "positioned for the current macro setup, and what would change your read."
        ),
        "default_includes": ["quotes", "macro", "treasury", "fundamentals", "filings", "news"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
]


def seed_presets(apps, schema_editor):
    AgentPreset = apps.get_model("profiles", "AgentPreset")
    # Also called by apps/profiles/tests/conftest.py with the LIVE registry (re-seeding
    # after serialized_rollback wipes the builtins) — filter to the model's current
    # fields so keys later migrations removed don't FieldError there. No-op for the
    # historical registry, where every key is valid.
    fields = {f.name for f in AgentPreset._meta.get_fields()}
    for preset in BUILTINS:
        AgentPreset.objects.get_or_create(
            slug=preset["slug"],
            defaults={k: v for k, v in preset.items() if k != "slug" and k in fields},
        )


def unseed_presets(apps, schema_editor):
    AgentPreset = apps.get_model("profiles", "AgentPreset")
    AgentPreset.objects.filter(slug__in=[p["slug"] for p in BUILTINS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("profiles", "0007_tradingprofile_enable_coach"),
    ]

    operations = [
        migrations.RunPython(seed_presets, reverse_code=unseed_presets),
    ]
