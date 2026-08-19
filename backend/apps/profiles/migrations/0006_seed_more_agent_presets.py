from __future__ import annotations

from django.db import migrations

BUILTINS = [
    {
        "slug": "morning-gameplan",
        "name": "Morning game plan",
        "description": "Pre-open plan: overnight moves, gaps, catalysts, and levels to watch.",
        "objective_template": (
            "Build a pre-open game plan. Summarize overnight and pre-market moves across the watchlist, "
            "flag any notable gaps and what's driving them, list today's catalysts (earnings, macro prints, "
            "scheduled events), and lay out the key technical levels for each name. Finish with where you'd "
            "be a buyer, where you'd be a seller, and what would keep you on the sidelines today."
        ),
        "default_includes": ["quotes", "ohlc", "news", "events", "breadth"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "closing-wrap",
        "name": "Closing wrap",
        "description": "End-of-day: what actually changed vs the open and what to carry overnight.",
        "objective_template": (
            "Write an end-of-day wrap. For each position and watchlist name, state what materially changed "
            "today versus the morning setup — which theses strengthened, which weakened, and why. Call out "
            "any technical breaks or confirmations on the day, summarize the news that moved things, and end "
            "with what you'd carry overnight and what you'd want to revisit at tomorrow's open."
        ),
        "default_includes": ["quotes", "positions", "ohlc", "news"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "risk-audit",
        "name": "Risk audit",
        "description": "Portfolio-level concentration, correlated exposure, and sizing outliers.",
        "objective_template": (
            "Audit the portfolio for risk, not opportunity. Identify concentration (single-name and sector), "
            "names that are likely correlated and would move together in a drawdown, and position-size outliers "
            "relative to the rest of the book. Estimate a plausible worst-case drawdown given current breadth "
            "and volatility, and recommend the single highest-impact change to reduce risk."
        ),
        "default_includes": ["quotes", "positions", "breadth"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "income-setup",
        "name": "Premium / income setup",
        "description": "Find rich IV for premium selling — strikes, deltas, expirations, assignment risk.",
        "objective_template": (
            "Scan for premium-selling setups. Using the option chain, identify where implied volatility looks "
            "rich relative to the recent realized move, and propose specific strikes, deltas, and expirations "
            "for cash-secured puts or covered calls. For each idea, state the premium captured, the breakeven, "
            "the probability of assignment, and what technical level would make you uncomfortable holding it."
        ),
        "default_includes": ["quotes", "ohlc", "chain"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "macro-read",
        "name": "Macro & rotation read",
        "description": "Breadth + macro calendar → which sectors and regimes are in favor.",
        "objective_template": (
            "Read the macro backdrop and sector rotation. Use market breadth to judge whether the tape is "
            "broad or narrow, risk-on or risk-off, then connect that to the upcoming macro calendar (CPI, FOMC, "
            "jobs, etc.) and the news flow. Conclude with which sectors or regimes look to be gaining or losing "
            "favor, and what a rotation would imply for the current watchlist."
        ),
        "default_includes": ["breadth", "events", "news"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "catalyst-scan",
        "name": "Catalyst scan",
        "description": "News + events → upcoming catalysts ranked by likely impact.",
        "objective_template": (
            "Scan for upcoming catalysts across the watchlist. Combine scheduled events (earnings, macro prints, "
            "product dates) with the current news flow, then rank the catalysts most-impactful-first. For each, "
            "name which positions or watchlist names are exposed, the direction of the likely surprise if there "
            "is a lean, and the time window to watch."
        ),
        "default_includes": ["news", "events", "quotes"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "breakout-scan",
        "name": "Technical breakout scan",
        "description": "OHLC-driven: names breaking key levels with volume confirmation.",
        "objective_template": (
            "Run a technical breakout scan. From the price history, identify watchlist names breaking out of (or "
            "breaking down from) meaningful levels — ranges, trendlines, prior highs/lows — and assess whether "
            "volume confirms the move. For each candidate, give a specific entry trigger, an invalidation level, "
            "and a measured-move target, and rank them by setup quality."
        ),
        "default_includes": ["quotes", "ohlc", "breadth"],
        "structured": False,
        "builtin": True,
        "active": True,
    },
    {
        "slug": "trade-postmortem",
        "name": "Trade post-mortem",
        "description": "Review a closed or decided trade: what the thesis got right and wrong.",
        "objective_template": (
            "Run a post-mortem on the trade described in the objective. Reconstruct the original thesis, then "
            "compare it against what actually happened in the price and news. Separate what the thesis got right "
            "from what it got wrong, and distinguish good-process-bad-outcome from genuine analytical errors. "
            "Finish with one or two concrete, repeatable process changes for next time."
        ),
        "default_includes": ["quotes", "ohlc", "news"],
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
        ("profiles", "0005_seed_agent_presets"),
    ]

    operations = [
        migrations.RunPython(seed_presets, reverse_code=unseed_presets),
    ]
