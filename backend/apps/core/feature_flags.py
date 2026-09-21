"""Authoritative inventory of the project's boolean feature flags.

Every behavioural ``env.bool("...")`` toggle in ``config/settings`` is registered here
with its default, category, and a one-line summary.  This is the single source of
truth the drift guard (``apps/core/tests/test_feature_flag_inventory.py``) checks
against the settings source: a flag added to settings without an entry here — or an
entry that outlives its flag — fails CI.  It mirrors the OpenAPI/schema drift gates,
applied to env configuration.

Why bother: every opt-in flag roughly *doubles* the behaviour-space the test suite
must cover, and the suite can't test the cross-product.  Making the set legible and
gated is the cheapest brake on that combinatorial growth.  See ``docs/feature-flags.md``
for the narrative and the graduation/kill policy.

Product flags ship ON: every capability the app has is reachable out of the box, and
this inventory — not a README — is the drift-gated source of truth for what the
default actually is.  Each one stays switchable from Settings → Features, which writes
the matching ``SystemSettings`` override; a NULL override inherits the default below.
``RETURNS_ADJUST_DIVIDENDS`` is the single product flag that defaults OFF, because
turning it on restates already-recorded post-mortem history.  ``category`` separates
genuine product toggles from infra/test switches that merely happen to be ``env.bool``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal["feature", "infra", "test"]


@dataclass(frozen=True)
class FeatureFlag:
    name: str
    default: bool
    category: Category
    summary: str


# Keep alphabetised within each category block for easy scanning.
FEATURE_FLAGS: list[FeatureFlag] = [
    # --- infra / test: env.bool switches that are NOT product features ---
    FeatureFlag(
        "DJANGO_DEBUG",
        False,
        "infra",
        "Django debug mode — dev only; must never be on in prod.",
    ),
    FeatureFlag(
        "MOCK_EXTERNAL",
        False,
        "test",
        "Short-circuit the AI/Schwab/Finnhub clients to canned fixtures (E2E overlay). "
        "Never set on the normal dev stack — provider tests would hit the mock.",
    ),
    # --- product features: each a behaviour-space branch, each UI-switchable ---
    FeatureFlag(
        "AI_CALIBRATION_ROUTING_ENABLED",
        True,
        "feature",
        "Router fallback tier picks the best-measured (provider, model) from recent EvalRuns.",
    ),
    FeatureFlag(
        "AI_FAILOVER_ENABLED",
        True,
        "feature",
        "Retry once on a secondary provider when the primary errors before emitting any token.",
    ),
    FeatureFlag(
        "AIEVAL_SCHEDULED_ENABLED",
        True,
        "feature",
        "Run the calibration eval on a beat schedule — spends real AI $ (the beat task refuses under MOCK_EXTERNAL).",
    ),
    FeatureFlag(
        "BOOK_NARRATIVE_ENABLED",
        True,
        "feature",
        "Layer an AI paragraph onto the daily whole-book risk reading. Off keeps the "
        "computed numbers and drops only the prose.",
    ),
    FeatureFlag(
        "CALIBRATION_DRIFT_SENTINEL_ENABLED",
        True,
        "feature",
        "Daily sentinel: notify when a model's calibration_error drifts (over/under-confident). No AI $.",
    ),
    FeatureFlag(
        "ANOMALY_SWEEP_ENABLED",
        True,
        "feature",
        "Arm the beat-scheduled Desk sweep: scan watched tickers and auto-originate DeskEntry investigations.",
    ),
    FeatureFlag(
        "OBSERVER_RESPONSE_CACHE_ENABLED",
        True,
        "feature",
        "Reuse a byte-identical recent observer prompt's response instead of paying for another AI call.",
    ),
    FeatureFlag(
        "REGIME_NARRATIVE_ENABLED",
        True,
        "feature",
        "Layer an AI paragraph onto each market-regime reading. Off keeps the computed "
        "axes and drops only the prose.",
    ),
    FeatureFlag(
        "RESTORE_FROM_UI_ENABLED",
        True,
        "feature",
        "Allow restoring the database from a backup in the UI — the one destructive action in the app.",
    ),
    FeatureFlag(
        "RETURNS_ADJUST_DIVIDENDS",
        False,
        "feature",
        "Dividend-adjust forward-return math in apps.market.returns — retroactive, so it restates "
        "post-mortem/Scorecard/Mirror history already computed under price-return. Defaults OFF.",
    ),
    FeatureFlag(
        "TRADINGVIEW_TOOLS_ENABLED",
        True,
        "feature",
        "Expose the read-only tv_* TradingView MCP tools to the in-app AI (needs a connected TradingView).",
    ),
]


def flag_names() -> set[str]:
    """Set of registered env-var names — the canonical side of the drift gate."""
    return {f.name for f in FEATURE_FLAGS}
