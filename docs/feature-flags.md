# Feature flags

A living inventory of the project's boolean feature flags — the `env.bool(...)`
toggles in `backend/config/settings/`.

**Authoritative, machine-checked list:** [`backend/apps/core/feature_flags.py`](../backend/apps/core/feature_flags.py).
A drift gate (`backend/apps/core/tests/test_feature_flag_inventory.py`) fails CI if a
flag is added to settings without a registry entry, or a registry entry outlives its
flag. This page is the human narrative; the registry is the source of truth.

**For the full switch inventory, read [`toggles.md`](toggles.md)** — 91 switches,
generated from `apps/core/features.py`. This page covers only the env-var layer: the
eleven product flags and the two infra/test switches that are not features at all.

## What a flag means here

A product flag is a **default**, not a setting. Each one is also a row on
**Settings → Features**, which writes a `SystemSettings` override; a NULL override
inherits the flag. So the environment variable answers "what does a fresh install do",
and the Features page answers "what does this install do". A gate
(`test_every_product_feature_flag_is_reachable_from_the_registry`) fails when a product
flag has no UI row.

Every product flag ships **on** except `RETURNS_ADJUST_DIVIDENDS`, which is retroactive
— see the note below the table.

## Why the inventory exists

Every flag is a branch of behaviour the test suite must cover, and the suite cannot
cover the cross-product. Four booleans are already sixteen combinations. Listing them
in one gated place is the cheapest brake on that growth: the question a new flag has to
answer is not "should it default on" but "does this knob earn a permanent branch".
A knob whose answer is a one-time methodology decision belongs in the code, not in an
env var.

## Infra / test switches

These are `env.bool` switches but not product features, and a drift gate keeps them off
the Features page forever: a UI-settable `MOCK_EXTERNAL` would make every provider
return canned fixtures while the app looked normal.

| Flag | Default | UI-switchable? where? | What ON does |
|---|---|---|---|
| `DJANGO_DEBUG` | OFF | No — excluded by gate | Django debug mode. Dev only; never prod. |
| `MOCK_EXTERNAL` | OFF | No — excluded by gate | Canned AI/Schwab/Finnhub fixtures (E2E overlay). Never on the dev stack. |

## Product features

| Flag | Default | UI-switchable? where? | What ON does |
|---|---|---|---|
| `AI_CALIBRATION_ROUTING_ENABLED` | ON | Settings → Features (AI capabilities) | Router fallback tier picks the best-measured `(provider, model)` from recent evals. Below the scored-call floor it no-ops. |
| `AI_FAILOVER_ENABLED` | ON | Settings → Features (AI capabilities) | Retry once on a secondary provider when the primary errors before emitting a token. |
| `AIEVAL_SCHEDULED_ENABLED` | ON | Settings → Features (Autonomous spend) | Run the calibration eval on a beat. Spends real AI $; the beat task refuses under `MOCK_EXTERNAL`. |
| `ANOMALY_SWEEP_ENABLED` | ON | Settings → Features (Autonomous spend) | Arm the beat-scheduled Desk sweep; auto-originate `DeskEntry` investigations. Spends real AI $; refuses under `MOCK_EXTERNAL`. |
| `BOOK_NARRATIVE_ENABLED` | ON | Settings → Features (Observation & automation) | Layer an AI paragraph onto the daily whole-book risk reading. Off keeps every computed number. |
| `CALIBRATION_DRIFT_SENTINEL_ENABLED` | ON | Settings → Features (Observation & automation) | Daily sentinel that notifies once per episode when a model's `calibration_error` drifts. Reads `EvalRun`s only; no AI $. |
| `OBSERVER_RESPONSE_CACHE_ENABLED` | ON | Settings → Features (Observation & automation) | Reuse a byte-identical recent observer prompt's response instead of paying for another AI call. |
| `REGIME_NARRATIVE_ENABLED` | ON | Settings → Features (Observation & automation) | Layer an AI paragraph onto each market-regime reading. Off keeps every computed axis. |
| `RESTORE_FROM_UI_ENABLED` | ON | Settings → Features (Danger zone) | Allow restoring the database from a backup in the UI — the one irreversible action in the app. |
| `RETURNS_ADJUST_DIVIDENDS` | **OFF** | Settings → Features (Methodology) | Dividend-adjust forward-return math (price-return → total-return) across all calibration. |
| `TRADINGVIEW_TOOLS_ENABLED` | ON | Settings → Features (AI capabilities), and the TradingView connection card | Expose the read-only `tv_*` TradingView MCP tools to the in-app AI. Inert until a TradingView account is connected. |

### The one flag that ships off

`RETURNS_ADJUST_DIVIDENDS` is **retroactive**. Splits are always adjusted; dividends are
the methodology choice, and every post-mortem, Scorecard and Mirror number is derived
from the same stored bars on read. Turning it on does not recompute anything — it
restates what the record already says, so one history would carry two methodologies.
It is a decision to take once, before there is a record worth keeping.

### The two flags that spend money unattended

`ANOMALY_SWEEP_ENABLED` and `AIEVAL_SCHEDULED_ENABLED` are the only scheduled tasks that
can originate provider calls nobody asked for. Three things bound them: the autonomous
daily cap (`AI_AUTONOMOUS_DAILY_CAP_USD`, Settings → Features), the per-provider daily
and monthly caps, and a `MOCK_EXTERNAL` refusal inside each task, which stops an armed
beat schedule in the e2e overlay before it does any work (`run_structured` also returns
a canned instance under `MOCK_EXTERNAL`, so the billable call is blocked twice).
`test_gated_spending_tasks_name_a_real_flag` enforces that a
`spends=True` scheduled task names a registered flag, so this stays switchable rather
than becoming unconditional.

## Related (not gated here)

- `SENTRY_DSN` — a presence-based toggle (`env.str`; error tracking initialises only
  when set), not an `env.bool`, so it's documented here but outside the drift gate.
- Numeric **tuning knobs** (caps, TTLs, horizons, budgets) use `env.int` / `env.float`
  and are *parameters*, not on/off features, so they're out of scope for this
  inventory. Many of them are `SystemSettings`-backed and do appear on the Features
  page; [`toggles.md`](toggles.md) lists all of them with their defaults.
- Per-object switches (a profile's capabilities, a schedule's modes, a trigger's
  cooldown) are model fields, not env vars. They are in [`toggles.md`](toggles.md) too.
- The runtime-override mechanism itself — `apps.core.SystemSettings` /
  `runtime_config()` — is described in CLAUDE.md → "UI-configurable runtime settings".
