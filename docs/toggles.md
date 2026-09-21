# What can be toggled, and where

91 switches. 39 are app-wide. The other 52 are the value one new profile, provider, preset, schedule, trigger, thesis or lesson starts with, so the same row reads differently for every object you own.

**App-wide capabilities: 12 of the 13 that are simply on or off ship on.** Dividend-adjusted return math is the single exception, and the [reason](#the-one-app-wide-capability-that-ships-off) is that it rewrites numbers already recorded. The remaining 26 app-wide rows are not on/off at all: they hold a value — a retention window, a spend ceiling, a model id — or state a constant.

**Per-object defaults: 22 ship on and 15 ship off.** An off here is a starting value, not a capability held back from you:

- **8 per profile** — Chart image, Company fundamentals, Fed communication, Flow proxy (volume-based), Notes, Overnight board, SEC filings, Treasury.
- **3 per schedule** — Batch submission, Cross-model consensus, Structured observation.
- **2 per lesson** — Lesson muted, Lesson pinned.
- **1 per preset** — Built-in preset.
- **1 per thesis** — Thesis invalidation guard.

The other 15 per-object rows hold a value rather than a state. Each row below names where it is set, including the ones that are read-only markers rather than switches.

**Settings → Features** renders from this same registry, in the same groups, with the same copy. App-wide switches are edited in place there, bar the [rows that stay read-only](#not-switchable-from-the-ui-and-why); a switch that lives on an object shows how many objects currently have it on and links to the page that owns it.

9 switches bill a model provider when they are on; they are collected under [Toggles that spend money](#toggles-that-spend-money) as well as listed in their own group.

## How to read the tables

- **Where to change it** names the surface that owns the value. `Settings → Features` means the switch is editable in place on that page.
- **Default** is what a fresh install runs with. Global switches store nothing until you change one: an empty override inherits the default, so clearing a value is how you get back to the column below.
- **Costs money** marks a switch whose purpose is to add provider calls. It is not the whole cost surface — richer capture sections, more tool rounds and more watched tickers all change the size of calls you already pay for.

## AI capabilities

What the models are allowed to do, and which one answers.

| What it does | Where to change it | Default | Costs money |
|---|---|---|---|
| **Cross-provider failover** — Retry a failed run once on a secondary provider. | Settings → Features | On | No |
| **Failover provider** — Which provider catches a failed run. Empty picks one automatically. _(needs Cross-provider failover)_ | Settings → Features | empty | No |
| **Route by measured calibration** — The fallback tier picks the best-measured model from recent evals. | Settings → Features | On | No |
| **Minimum scored calls** — Below this many scored eval calls, a measurement is ignored. _(needs Route by measured calibration)_ | Settings → Features | 5 calls | No |
| **Maximum eval age** — Evals older than this no longer pin routing. _(needs Route by measured calibration)_ | Settings → Features | 30 days | No |
| **TradingView tools for the AI** — Expose the read-only tv_* MCP tools to tool-enabled runs. _(needs a connected TradingView)_ | Settings → Features | On | No |
| **Chat tool rounds** — Ceiling on tool calls in one ordinary (non-investigation) run. | Settings → Features | 12 rounds | No |
| **Provider retry attempts** — SDK-level retries on a transport error. Environment only. | Environment variable, then restart | 2 attempts | No |
| **Provider request timeout** — How long a provider call may hang before it is abandoned. Environment only. | Environment variable, then restart | 60 seconds | No |
| **AI tools (function calling)** — Let this profile's runs call quote, OHLC, news, chain and indicator tools. | Profiles page, per profile | On | No |
| **Extended thinking** — Give Claude a private reasoning budget before it answers. _(Claude only)_ | Profiles page, per profile | On | Yes |
| **Thinking budget** — Token ceiling for extended thinking on this profile. _(Claude only)_ | Profiles page, per profile | 8,000 | No |
| **Reasoning effort** — How hard the model works on this profile's runs. _(Claude only)_ | Profiles page, per profile | `high` | No |
| **Memory tool** — A per-profile scratchpad the model can write to and read back. _(Claude only)_ | Profiles page, per profile | On | No |
| **Decision Coach context** — Inject prior theses, your track record and recalled notes into the prompt. | Profiles page, per profile | On | No |
| **Profile active** — Whether the profile is offered when capturing. | Profiles page, per profile | On | No |
| **Default provider** — Which provider this profile's runs go to by default. | Profiles page, per profile | `claude` | No |
| **Default model** — The model id this profile pins. | Profiles page, per profile | `claude-sonnet-4-6` | No |
| **Default capture sections** — Which snapshot sections a capture with this profile collects. | Profiles page, per profile | quotes, positions, breadth, ohlc, chain, news, events, macro | No |
| **Provider enabled** — Whether a configured provider may be selected at all. | Settings → AI Providers page, per provider | On | No |
| **Provider accepts images** — Whether chart images may be attached to this provider's runs. | Settings → AI Providers page, per provider | On | No |
| **Provider accepts tools** — Gates tool use for OpenAI and local endpoints. | Settings → AI Providers page, per provider | On | No |
| **Preset offered in the composer** — Whether a capture preset appears in the objective picker. | Profiles page, per preset | On | No |
| **Built-in preset** — Marks a preset that shipped with the app. Read-only by design. | Read-only | Off | No |
| **Lesson pinned** — A pinned lesson reaches the Coach regardless of how thin its evidence is. | Lessons page, per lesson | Off | No |
| **Lesson muted** — A muted lesson is withheld from the Coach. | Lessons page, per lesson | Off | No |

## Observation & automation

Everything that runs without you asking: schedules, triggers, the briefing.

| What it does | Where to change it | Default | Costs money |
|---|---|---|---|
| **Observer response cache** — Reuse a recent observation when the prompt is byte-identical. | Settings → Features | On | No |
| **Response cache lifetime** — How long a cached observation stays reusable. _(needs Observer response cache)_ | Settings → Features | 1,800 seconds | No |
| **Calibration drift alerts** — Notify when a model becomes measurably over- or under-confident. | Settings → Features | On | No |
| **Regime narrative** — Layer an AI paragraph onto each market-regime reading. | Settings → Features | On | Yes |
| **Book narrative** — Layer an AI paragraph onto the daily whole-book risk reading. | Settings → Features | On | Yes |
| **Schedule timezone** — The timezone cron expressions are evaluated in. Environment only. | Environment variable, then restart | `UTC` | No |
| **Trigger evaluation interval** — How often armed triggers are evaluated. Environment only. | Environment variable, then restart | 10 seconds | No |
| **Schedule armed** — Whether a scheduled observation fires at all. | Schedules page, per schedule | On | No |
| **Market hours only** — Skip fires outside the NYSE session. | Schedules page, per schedule | On | No |
| **Payload mode** — Send the full capture, or only what changed since the last one. | Schedules page, per schedule | `full` | No |
| **Structured observation** — Return a validated report object instead of streamed prose. | Schedules page, per schedule | Off | No |
| **Batch submission** — Submit fires as a Messages Batch — about half price, not interactive. _(Claude only)_ | Schedules page, per schedule | Off | No |
| **Cross-model consensus** — Run the same structured report on every usable provider and compare. _(needs Structured observation)_ | Schedules page, per schedule | Off | Yes |
| **Investigate on fire** — Run a bounded tool-using investigation instead of a single observation. | Schedules page, per schedule | On | Yes |
| **Fire mode** — Fire on a cron expression, or relative to the real session close. | Schedules page, per schedule | `cron` | No |
| **Minutes before close** — How far ahead of the real close a relative schedule fires. | Schedules page, per schedule | 5 | No |
| **Provider override** — Send this schedule's fires to a provider other than the profile's. | Schedules page, per schedule | empty | No |
| **Model override** — Pin a specific model for this schedule's fires. | Schedules page, per schedule | empty | No |
| **Schedule capture sections** — Override which sections this schedule's captures collect. | Schedules page, per schedule | empty | No |
| **Schedule tickers** — Restrict this schedule's captures to specific tickers. | Schedules page, per schedule | empty | No |
| **Trigger armed** — Whether a condition rule is evaluated on the tick. | Triggers page, per trigger | On | No |
| **Investigate on trigger fire** — A fire runs a bounded tool-using investigation, not one observation. | Triggers page, per trigger | On | Yes |
| **Trigger cooldown** — Minimum quiet period between two fires of the same rule. | Triggers page, per trigger | 1,800 seconds | No |
| **Morning briefing** — Assemble and post one briefing per local day. | Settings → Features, or the Briefing page | On | No |
| **Briefing AI synthesis** — Pay for one model pass that reads the assembled briefing. | Settings → Features, or the Briefing page | On | Yes |
| **Briefing time** — Local time after which the day's briefing is assembled. | Settings → Features, or the Briefing page | 08:30 | No |
| **Briefing news window** — How far back the briefing gathers headlines. | Settings → Features, or the Briefing page | 14 hours | No |
| **Briefing event horizon** — How far forward the briefing looks for earnings and macro events. | Settings → Features, or the Briefing page | 7 days | No |
| **Briefing trading profile** — Which trading style frames the briefing. Object reference, not a switch. | Not switchable | empty | No |
| **Thesis invalidation guard** — Auto-create a trigger that watches a thesis's invalidation level. | Theses page, per thesis | Off | No |

## Autonomous spend

Background work that bills a provider, and the ceilings that bound it.

| What it does | Where to change it | Default | Costs money |
|---|---|---|---|
| **Autonomous daily cap** — Stops unattended investigations once the provider's day reaches this. | Settings → Features | $5.00 | No |
| **Investigation tool rounds** — Ceiling on tool calls inside one autonomous investigation. | Settings → Features | 8 rounds | No |
| **Scheduled anomaly sweep** — Scan watched tickers on a schedule and open Desk investigations unasked. | Settings → Features | On | Yes |
| **Scheduled calibration eval** — Replay decided theses against a model on a schedule to score it. | Settings → Features | On | Yes |
| **Eval model** — Which model the scheduled eval scores. _(needs Scheduled calibration eval)_ | Settings → Features | `claude-sonnet-4-6` | No |
| **Eval horizon** — Which post-mortem horizon the eval scores against. _(needs Scheduled calibration eval)_ | Settings → Features | 30 days | No |
| **Eval row limit** — How many theses one scheduled eval replays. _(needs Scheduled calibration eval)_ | Settings → Features | 25 rows | No |
| **Provider daily cap** — Hard daily spend ceiling per provider. | Settings → AI Providers page, per provider | $10.00 | No |
| **Provider monthly cap** — Rolling 30-day spend ceiling per provider. Empty means none. | Settings → AI Providers page, per provider | — | No |

## Data & retention

What each capture collects and how long it is kept.

| What it does | Where to change it | Default | Costs money |
|---|---|---|---|
| **OHLC bars** — How long price bars are kept before the nightly purge. | Settings → Features | 400 days | No |
| **Option chains** — How long captured option chains are kept before the nightly purge. | Settings → Features | 120 days | No |
| **Notifications** — How long notifications are kept before the nightly purge. | Settings → Features | 90 days | No |
| **Resolved errors** — How long resolved error events are kept before the nightly purge. | Settings → Features | 90 days | No |
| **Regime readings** — How long market-regime readings are kept before the nightly purge. | Settings → Features | 180 days | No |
| **Desk findings** — How long desk findings are kept before the nightly purge. | Settings → Features | 180 days | No |
| **Book snapshots** — How long whole-book risk snapshots are kept before the nightly purge. | Settings → Features | 365 days | No |
| **Quotes** — Include the quotes section in a capture's payload. | Profiles page, per profile | On | No |
| **OHLC** — Include the ohlc section in a capture's payload. | Profiles page, per profile | On | No |
| **Option chain** — Include the option chain section in a capture's payload. | Profiles page, per profile | On | No |
| **Positions** — Include the positions section in a capture's payload. | Profiles page, per profile | On | No |
| **Market breadth** — Include the market breadth section in a capture's payload. | Profiles page, per profile | On | No |
| **News** — Include the news section in a capture's payload. | Profiles page, per profile | On | No |
| **Upcoming events** — Include the upcoming events section in a capture's payload. | Profiles page, per profile | On | No |
| **Macro** — Include the macro section in a capture's payload. | Profiles page, per profile | On | No |
| **Company fundamentals** — Include the company fundamentals section in a capture's payload. | Profiles page, per profile | Off | No |
| **SEC filings** — Include the sec filings section in a capture's payload. | Profiles page, per profile | Off | No |
| **Treasury** — Include the treasury section in a capture's payload. | Profiles page, per profile | Off | No |
| **Overnight board** — Include the overnight board section in a capture's payload. | Profiles page, per profile | Off | No |
| **Chart image** — Include the chart image section in a capture's payload. | Profiles page, per profile | Off | No |
| **Notes** — Include the notes section in a capture's payload. | Profiles page, per profile | Off | No |
| **Fed communication** — Include the fed communication section in a capture's payload. | Profiles page, per profile | Off | No |
| **Flow proxy (volume-based)** — Include the flow proxy (volume-based) section in a capture's payload. | Profiles page, per profile | Off | No |
| **VIX term structure** — Always on. Every capture path appends it, and it is never pruned. | Not switchable | Always on | No |

## Methodology

How recorded performance is computed. Changing it rewrites history.

| What it does | Where to change it | Default | Costs money |
|---|---|---|---|
| **Dividend-adjusted (total-return) math** — Compute forward returns on a total-return basis instead of price-return. _(**retroactive**)_ | Settings → Features | Off | No |

## Danger zone

One switch, and it ships on: the UI may overwrite the live database from a backup. Turn it off on any machine other people can reach, which leaves the command-line restore as the only path.

| What it does | Where to change it | Default | Costs money |
|---|---|---|---|
| **Restore from backup in the UI** — Allow overwriting the live database from a backup without a shell. | Settings → Features | On | No |

## Toggles that spend money

Each of these adds provider calls when it is on. The per-provider daily and monthly caps bound all of them, and the autonomous daily cap bounds the unattended ones on top of that; a run over a cap is skipped and recorded as skipped rather than failing silently.

| Switch | Where to change it | Default | What it costs |
|---|---|---|---|
| **Scheduled anomaly sweep** | Settings → Features | On | Runs unattended every 30 minutes and can start investigations without you. |
| **Scheduled calibration eval** | Settings → Features | On | Each scheduled run replays up to the row limit below against a real model. |
| **Regime narrative** | Settings → Features | On | One short model call per regime refresh. |
| **Book narrative** | Settings → Features | On | One short model call per daily book snapshot. |
| **Extended thinking** | Profiles page, per profile | On | Thinking tokens bill as output tokens on every run of this profile. |
| **Cross-model consensus** | Schedules page, per schedule | Off | Multiplies each fire's cost by the number of usable providers. |
| **Investigate on fire** | Schedules page, per schedule | On | A bounded tool-using investigation costs several model calls per fire instead of one, capped by the investigation tool-round limit and the autonomous daily cap. |
| **Investigate on trigger fire** | Triggers page, per trigger | On | A bounded tool-using investigation costs several model calls per fire instead of one, capped by the investigation tool-round limit and the autonomous daily cap. |
| **Briefing AI synthesis** | Settings → Features, or the Briefing page | On | One model call per briefing, once per day. |

## The one app-wide capability that ships off

**Dividend-adjusted (total-return) math** (`RETURNS_ADJUST_DIVIDENDS`) — Compute forward returns on a total-return basis instead of price-return. Change it in Settings → Features.

**Retroactive.** Splits are always adjusted; dividends are the methodology choice. Turning this on restates every post-mortem, Scorecard and Mirror number already computed under price-return, because they are all derived from the same stored bars on read. Nothing is recomputed and stored — the numbers simply change. This is the one app-wide capability that ships off.

One recorded history would then carry two methodologies, which is what makes this a decision to take once rather than a switch to flip and unflip. Everything else in this document changes what happens next; this one changes what the record says about what already happened.

## Not switchable from the UI, and why

These appear on the Features page as read-only rows with their reason, rather than going quietly missing.

| Knob | Default | Why it stays out of the UI |
|---|---|---|
| **Schedule timezone** (`OBSERVER_BEAT_TIMEZONE`) | `UTC` | Stamped onto each schedule's beat row at save time. Changing it in the database would silently leave existing schedules on the old timezone. Set OBSERVER_BEAT_TIMEZONE in the environment before creating schedules. |
| **Trigger evaluation interval** (`TRIGGER_TICK_SECONDS`) | 10 seconds | Consumed once by a migration to create the beat interval row. The live value lives in that row, so editing the environment variable later has no effect. |
| **Provider retry attempts** (`AI_PROVIDER_MAX_RETRIES`) | 2 attempts | Read at provider __init__, which runs inside the async streaming loop — a database-backed override there would raise SynchronousOnlyOperation. Set AI_PROVIDER_MAX_RETRIES in the environment and restart. |
| **Provider request timeout** (`AI_PROVIDER_TIMEOUT_SECONDS`) | 60 seconds | Read at provider __init__ on the async streaming path — a database read there would raise SynchronousOnlyOperation. Set AI_PROVIDER_TIMEOUT_SECONDS in the environment and restart. |

Two more rows are stated constants rather than switches:

- **Briefing trading profile** — A reference to a trading profile, not an on/off value. Set it with PATCH /api/briefings/config/.
- **VIX term structure** — Always on by design: every capture path appends it and the token budget may not prune it.

### Deliberately excluded

- `DJANGO_DEBUG` and `MOCK_EXTERNAL` have no UI switch and a drift gate keeps them out. A UI-settable `MOCK_EXTERNAL` would make every provider return canned fixtures while the app looked normal.
- Credentials and connection settings are not features. **Settings → Connections** owns them: `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `POSTGRES_*`, `REDIS_URL`, `CELERY_*`, `ENCRYPTION_SALT_PATH`, `SNAPSHOT_IMAGE_DIR`, `RENDER_BASE_URL`, `FRONTEND_BASE_URL`, `SCHWAB_*`, `TRADINGVIEW_MCP_URL`, `TRADINGVIEW_MCP_CALLBACK_URL`, `SEC_EDGAR_USER_AGENT`, `SENTRY_DSN`, `MCP_AUTH_TOKEN`, `*_API_KEY`.

## Appendix: environment names

Every global switch also has an environment variable, which sets the default a cleared override falls back to. A value set in Settings → Features wins over the environment.

| Switch | Environment variable | Stored as |
|---|---|---|
| Scheduled calibration eval | `AIEVAL_SCHEDULED_ENABLED` | `SystemSettings` override, or the environment default |
| Eval horizon | `AIEVAL_SCHEDULED_HORIZON` | `SystemSettings` override, or the environment default |
| Eval row limit | `AIEVAL_SCHEDULED_LIMIT` | `SystemSettings` override, or the environment default |
| Eval model | `AIEVAL_SCHEDULED_MODEL` | `SystemSettings` override, or the environment default |
| Autonomous daily cap | `AI_AUTONOMOUS_DAILY_CAP_USD` | `SystemSettings` override, or the environment default |
| Route by measured calibration | `AI_CALIBRATION_ROUTING_ENABLED` | `SystemSettings` override, or the environment default |
| Maximum eval age | `AI_CALIBRATION_ROUTING_MAX_AGE_DAYS` | `SystemSettings` override, or the environment default |
| Minimum scored calls | `AI_CALIBRATION_ROUTING_MIN_SCORED` | `SystemSettings` override, or the environment default |
| Chat tool rounds | `AI_CHAT_MAX_TOOL_ITERATIONS` | `SystemSettings` override, or the environment default |
| Cross-provider failover | `AI_FAILOVER_ENABLED` | `SystemSettings` override, or the environment default |
| Failover provider | `AI_FAILOVER_PROVIDER` | `SystemSettings` override, or the environment default |
| Investigation tool rounds | `AI_INVESTIGATION_MAX_ITERATIONS` | `SystemSettings` override, or the environment default |
| Provider retry attempts | `AI_PROVIDER_MAX_RETRIES` | environment only |
| Provider request timeout | `AI_PROVIDER_TIMEOUT_SECONDS` | environment only |
| Book snapshots | `AI_RETENTION_BOOK_DAYS` | `SystemSettings` override, or the environment default |
| Option chains | `AI_RETENTION_CHAIN_DAYS` | `SystemSettings` override, or the environment default |
| Desk findings | `AI_RETENTION_DESK_DAYS` | `SystemSettings` override, or the environment default |
| Resolved errors | `AI_RETENTION_ERROR_DAYS` | `SystemSettings` override, or the environment default |
| Notifications | `AI_RETENTION_NOTIFICATION_DAYS` | `SystemSettings` override, or the environment default |
| OHLC bars | `AI_RETENTION_OHLC_DAYS` | `SystemSettings` override, or the environment default |
| Regime readings | `AI_RETENTION_REGIME_DAYS` | `SystemSettings` override, or the environment default |
| Scheduled anomaly sweep | `ANOMALY_SWEEP_ENABLED` | `SystemSettings` override, or the environment default |
| Book narrative | `BOOK_NARRATIVE_ENABLED` | `SystemSettings` override, or the environment default |
| Calibration drift alerts | `CALIBRATION_DRIFT_SENTINEL_ENABLED` | `SystemSettings` override, or the environment default |
| Schedule timezone | `OBSERVER_BEAT_TIMEZONE` | environment only |
| Observer response cache | `OBSERVER_RESPONSE_CACHE_ENABLED` | `SystemSettings` override, or the environment default |
| Response cache lifetime | `OBSERVER_RESPONSE_CACHE_TTL_SECONDS` | `SystemSettings` override, or the environment default |
| Regime narrative | `REGIME_NARRATIVE_ENABLED` | `SystemSettings` override, or the environment default |
| Restore from backup in the UI | `RESTORE_FROM_UI_ENABLED` | `SystemSettings` override, or the environment default |
| Dividend-adjusted (total-return) math | `RETURNS_ADJUST_DIVIDENDS` | `SystemSettings` override, or the environment default |
| TradingView tools for the AI | `TRADINGVIEW_TOOLS_ENABLED` | `SystemSettings` override, or the environment default |
| Trigger evaluation interval | `TRIGGER_TICK_SECONDS` | environment only |

---

Generated from `backend/apps/core/features.py` by `manage.py toggles_doc`. Add a toggle to the registry in the same change that adds the capability: `apps/core/tests/test_feature_registry.py` fails when a switch has no row, and `apps/core/tests/test_toggles_doc.py` fails when this file no longer matches the registry.
