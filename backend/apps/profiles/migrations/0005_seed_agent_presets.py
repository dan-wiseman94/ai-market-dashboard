from __future__ import annotations

from django.db import migrations

BUILTINS = [
    {
        "slug": "earnings-prep",
        "name": "Earnings prep",
        "description": "Prep for an upcoming earnings event.",
        "objective_template": (
            "Prep for the upcoming earnings. Pull consensus estimates and expectations from the news, "
            "extract the implied move from the option chain, identify key technical levels, "
            "and lay out beat/miss/in-line scenarios with how you'd expect the stock to react to each."
        ),
        "default_includes": ["quotes", "ohlc", "news", "chain"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "devils-advocate",
        "name": "Devil's advocate",
        "description": "Steel-man the bear case against current positions.",
        "objective_template": (
            "Argue the strongest possible BEAR case against the current positions and watchlist. "
            "Be specific: cite price levels, deteriorating technicals, macro risks, or narrative shifts. "
            "State explicitly what would invalidate the existing bull thesis for each name."
        ),
        "default_includes": ["quotes", "positions", "ohlc"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "pre-trade-bias-check",
        "name": "Pre-trade bias check",
        "description": "Surface cognitive biases and give a go/no-go.",
        "objective_template": (
            "Before entering the trade: name the cognitive biases most likely at play in this setup "
            "(anchoring, recency, FOMO, etc.), state the historical base rate for this kind of trade "
            "given the current breadth and technicals, then deliver a clear go/no-go verdict with "
            "the specific conditions that would change your answer."
        ),
        "default_includes": ["quotes", "ohlc", "breadth"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "triage-pass",
        "name": "Triage pass",
        "description": "Rank what needs attention right now.",
        "objective_template": (
            "Triage across all positions and watchlist names. Rank them most-urgent-first by what needs "
            "attention RIGHT NOW — stops at risk, catalysts today, technical breakdowns, position sizing "
            "outliers. Each entry gets one line explaining why it made the list."
        ),
        "default_includes": ["quotes", "positions", "breadth", "news"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
]


def seed_presets(apps, schema_editor):
    AgentPreset = apps.get_model("profiles", "AgentPreset")
    for preset in BUILTINS:
        AgentPreset.objects.get_or_create(
            slug=preset["slug"],
            defaults={k: v for k, v in preset.items() if k != "slug"},
        )


def unseed_presets(apps, schema_editor):
    AgentPreset = apps.get_model("profiles", "AgentPreset")
    AgentPreset.objects.filter(slug__in=[p["slug"] for p in BUILTINS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0004_agent_preset"),
    ]

    operations = [
        migrations.RunPython(seed_presets, reverse_code=unseed_presets),
    ]
