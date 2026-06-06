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

All flags currently ship OFF.  ``category`` separates genuine product toggles from
infra/test switches that merely happen to be ``env.bool``.
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
    # --- opt-in product features: all default OFF, each a behaviour-space branch ---
    FeatureFlag(
        "AI_CALIBRATION_ROUTING_ENABLED",
        False,
        "feature",
        "Router fallback tier picks the best-measured (provider, model) from recent EvalRuns.",
    ),
    FeatureFlag(
        "AI_FAILOVER_ENABLED",
        False,
        "feature",
        "Retry once on a secondary provider when the primary errors before emitting any token.",
    ),
    FeatureFlag(
        "AIEVAL_SCHEDULED_ENABLED",
        False,
        "feature",
        "Run the calibration eval on a beat schedule — spends real AI $ (no MOCK_EXTERNAL short-circuit).",
    ),
    FeatureFlag(
        "ANOMALY_SWEEP_ENABLED",
        False,
        "feature",
        "Arm the beat-scheduled Desk sweep: scan watched tickers and auto-originate DeskEntry investigations.",
    ),
    FeatureFlag(
        "OBSERVER_RESPONSE_CACHE_ENABLED",
        False,
        "feature",
        "Reuse a byte-identical recent observer prompt's response instead of paying for another AI call.",
    ),
    FeatureFlag(
        "RETURNS_ADJUST_DIVIDENDS",
        False,
        "feature",
        "Dividend-adjust forward-return math in apps.market.returns — a semantic change to all calibration.",
    ),
]


def flag_names() -> set[str]:
    """Set of registered env-var names — the canonical side of the drift gate."""
    return {f.name for f in FEATURE_FLAGS}
