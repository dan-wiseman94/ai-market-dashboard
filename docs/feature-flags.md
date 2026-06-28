# Feature flags

A living inventory of the project's boolean feature flags — the `env.bool(...)`
toggles in `backend/config/settings/`.

**Authoritative, machine-checked list:** [`backend/apps/core/feature_flags.py`](../backend/apps/core/feature_flags.py).
A drift gate (`backend/apps/core/tests/test_feature_flag_inventory.py`) fails CI if a
flag is added to settings without a registry entry, or a registry entry outlives its
flag. This page is the human narrative; the registry is the source of truth.

## Why this exists

Every opt-in flag roughly **doubles** the behaviour-space the test suite must cover,
and we can't test the cross-product. Two opt-in observer modes plus failover plus the
response cache is already 2⁴ = 16 combinations from four flags alone. Left ungoverned,
flags accumulate as permanent scar tissue. So each flag below carries a **disposition**:
a stated intent to graduate it to default-on, keep it a deliberate opt-in, or decide
its question once and delete it. Flags are not free; this is the brake.

All flags currently ship **OFF**.

## Infra / test switches

These are `env.bool` switches but not product features. They stay as-is.

| Flag | Disposition | What ON does |
|---|---|---|
| `DJANGO_DEBUG` | permanent (infra) | Django debug mode. Dev only; never prod. |
| `MOCK_EXTERNAL` | permanent (test) | Canned AI/Schwab/Finnhub fixtures (E2E overlay). Never on the dev stack. |

## Opt-in product features

| Flag | Disposition | What ON does |
|---|---|---|
| `OBSERVER_RESPONSE_CACHE_ENABLED` | **graduate candidate** — pure cost saver, low risk | Reuse a byte-identical recent observer prompt's response instead of paying for another AI call. |
| `AI_FAILOVER_ENABLED` | **graduate candidate** — resilience win once exercised | Retry once on a secondary provider when the primary errors before emitting a token. |
| `AI_CALIBRATION_ROUTING_ENABLED` | keep opt-in — needs more `EvalRun` evidence | Router fallback tier picks the best-measured `(provider, model)` from recent evals. |
| `AIEVAL_SCHEDULED_ENABLED` | **keep opt-in (permanent)** — spends real AI $ on a schedule | Run the calibration eval on a beat (no `MOCK_EXTERNAL` short-circuit). |
| `CALIBRATION_DRIFT_SENTINEL_ENABLED` | keep opt-in — reads only, no AI $ | Daily sentinel that notifies once per episode when a model's `calibration_error` drifts (over/under-confident). |
| `ANOMALY_SWEEP_ENABLED` | **keep opt-in (permanent)** — autonomy that spends $ | Arm the beat-scheduled Desk sweep; auto-originate `DeskEntry` investigations. |
| `RETURNS_ADJUST_DIVIDENDS` | **decide-and-delete candidate** — a methodology choice, not a perpetual toggle | Dividend-adjust forward-return math (price-return → total-return) across all calibration. |

### Notes on the dispositions

- **Graduate candidates** (`OBSERVER_RESPONSE_CACHE_ENABLED`, `AI_FAILOVER_ENABLED`):
  flip the default to `True` once each has on-path coverage and a short bake. When a
  flag graduates, delete it and make the behaviour unconditional — a graduated flag
  left in place is just more scar tissue.
- **Permanent opt-ins**: the cost/autonomy flags (`AIEVAL_SCHEDULED_ENABLED`,
  `ANOMALY_SWEEP_ENABLED`) should stay off-by-default forever — they spend money or
  act autonomously, and the safe default is inaction.
- **Decide-and-delete** (`RETURNS_ADJUST_DIVIDENDS`): price-return vs total-return is a
  one-time methodology decision. A perpetual flag here means every calibration number is
  ambiguous until you check the env. Pick one, bake it in, drop the flag.

## Related (not gated here)

- `SENTRY_DSN` — a presence-based toggle (`env.str`; error tracking initialises only
  when set), not an `env.bool`, so it's documented here but outside the drift gate.
- Numeric **tuning knobs** (caps, TTLs, horizons, budgets) use `env.int` / `env.float`
  and are *parameters*, not on/off features — they don't multiply the behaviour-space
  the way a boolean mode does, so they're intentionally out of scope for this inventory.
- UI-configurable runtime settings live in `apps.core.SystemSettings` /
  `runtime_config()` — a separate mechanism (see CLAUDE.md → "UI-configurable runtime
  settings").
