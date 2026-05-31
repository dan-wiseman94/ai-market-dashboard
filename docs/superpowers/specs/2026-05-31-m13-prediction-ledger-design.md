# M13 — The Prediction Ledger: first-class, self-scoring AI forecasts

**Written 2026-05-31.** Design spec for the next milestone after the M1–M12
program + the post-M12 improvement work (M7 eval-loop, Tier A/B/C — all merged).

> **How this spec was produced.** Brainstorming discipline (problem framing →
> alternatives with trade-offs → isolation/clarity → YAGNI), applied
> autonomously per the standing "pick sound defaults, don't stall on scope
> questions" directive rather than as an interactive dialogue. The design
> decisions are made here with rationale; genuinely-open forks are collected in
> §11 for the user to weigh in on. **Nothing is implemented yet** — this is the
> approval artifact; the implementation plan follows once the spec is accepted.

---

## 1. The problem: a one-sided learning loop

The product's stated thesis is a **self-correcting AI** — the whole M1→M12 arc
is: capture → observe → record decisions → measure outcomes → feed measurements
back into reasoning. But the loop is closed for only **one** of the two actors
who make forecasts in this system:

| Actor | Makes a forecast via | Tracked? | Auto-resolved? | Scored? | Fed back into reasoning? |
|---|---|---|---|---|---|
| **Trader** | `Thesis` (+ conviction, invalidation) | ✅ | ✅ `PostMortem` | ✅ scorecard | ✅ coach (`track_record`, `lessons`, calibration) |
| **The AI** | `ObservationReport.predicted_direction` / `_horizon_days` / `_confidence` on every structured fire | ❌ | ❌ | ❌ (live) | ❌ |

The AI states a falsifiable directional call **on every structured observer
fire** (`apps/observer/schemas.py:ObservationReport`). Today those calls:

- are used **offline** by the M7 eval harness (`apps/aieval`) to score *candidate*
  `(system, model)` pairs against **frozen** past snapshots, and
- otherwise **evaporate** the moment the fire completes.

There is no record of the prediction the AI *actually made* on a given day, no
resolution of whether it came true, and — critically — **the AI has no awareness
of its own live track record when it generates the next observation.** The
trader's coach knows "your conviction-4 bullish calls hit 60%"; the AI's coach
has no equivalent "*my* bullish 7-day calls on NVDA have hit 45% and I've been
over-confident."

**M13 closes the AI's half of the loop.** It promotes the AI's predictions to
first-class, auto-resolving, calibration-tracked entities — symmetric to
`Thesis`/`PostMortem` — and feeds the resulting live track record back into the
coach. This is the missing piece that makes "self-correcting AI" literally true
rather than aspirational.

## 2. Why this is the right next milestone

Three reasons it dominates the alternatives (see §3):

1. **It builds on everything shipped, inventing almost no new machinery.** The
   prediction source already exists (`predicted_direction` et al.); the
   resolution pattern already exists (`run_postmortem`'s idempotent claim +
   `objective_verdict` + `returns.py`); the scoring already exists
   (`apps/analytics/services/calibration.py`); the feedback channel already
   exists (the decision coach). M13 is mostly **wiring proven parts into a
   second, symmetric loop**, not green-field building.
2. **It completes the product's only stated thesis.** Everything else is breadth;
   this is the one feature that finishes the depth story the product has been
   telling since M6.
3. **It produces a genuinely novel signal: triangulated calibration.** With M13
   the scorecard carries **three** independent calibration sources for the same
   models — trader theses, **offline eval** (frozen replay), and **live AI
   predictions** (actual calls). Disagreement between them is diagnostic: e.g.
   "offline eval says model X is well-calibrated, but X's *live* predictions run
   over-confident" reveals distribution shift the offline harness structurally
   cannot see.

## 3. Alternatives considered (and why not)

Each was a candidate theme for "more features building on these."

- **A. The Prediction Ledger (chosen).** Track + resolve + score + feed-back the
  AI's own forecasts. Highest "builds on these"; completes the thesis. *Chosen.*
- **B. Calibration-weighted provider routing only.** Make the eval loop *act* on
  its measurements by routing to the best-calibrated model. Powerful, but narrow
  and premature on its own — routing is only trustworthy once there's a **live**
  calibration signal to route on, which is exactly what A provides. So B is
  absorbed as **M13 Phase 3 (F6)**, not a standalone milestone.
- **C. Narrative / regime tracking.** Persistent "narratives" (AI-capex,
  rate-cut) that snapshots/theses/news/predictions attach to, plus a regime
  classifier. Compelling and a natural *future* (predictions are a prerequisite
  attachment), but more speculative and larger; defer to a later milestone that
  can hang off the ledger.
- **D. Scenario / what-if trees.** AI authors conditional ("if SPX < X then …")
  scenarios that resolve. Interesting but high-complexity and overlaps triggers;
  a prediction *is* the degenerate one-node scenario, so build the ledger first.
- **E. Multi-asset / new data domains (crypto, FX).** Breadth, not depth — does
  **not** build on the shipped reasoning loop. Out of scope for "building on
  these."

## 4. Architecture overview

A new Django app **`apps.predictions`**, parallel in spirit to `apps.thesis`:

```
observer structured/consensus fire
        │  (produces ObservationReport with a directional call)
        ▼
  extract_prediction()                         ← F1  (explicit call, no signals)
        │
        ▼
  AIPrediction(open)  ──schedule resolve_at = predicted_at + horizon
        │
        ├── predictions.resolve_due  (beat)    ← F2  idempotent claim → returns.py → verdict
        │        └─► AIPrediction(resolved, forward_return_pct, verdict)
        │
        ├── predictions.check_invalidations (beat) ← F5  price breached invalidation → notify
        │
        ▼
  ai_prediction_calibration()                  ← F3  3rd scorecard track + drilldown
        │
        ▼
  coach._ai_track_record_block(ticker, profile) ← F4  inject the AI's OWN live accuracy
        │
        ▼
  router calibration-weighted selection (opt-in) ← F6  the loop finally ACTS
```

**Import hygiene** (mirrors the `thesis` ↔ `threads` discipline in CLAUDE.md):
`apps.predictions.models` imports `apps.threads.models` (FKs to `Message`/`AIRun`)
and `apps.snapshots.models` — never the reverse. Code that *reads* predictions
from inside `threads`/`observer` (the coach block, the extraction call) uses
**lazy, function-local imports**, exactly as `coach.py` already does for
`thesis`. No new import cycle.

**Reuse, don't reinvent:**
- Resolution copies `run_postmortem`'s idempotent `scheduled→running` claim
  (`apps/thesis/services/postmortem.py`) so the beat task and a "resolve-now"
  button can't double-bill.
- Forward returns go through `apps/market/returns.py` (so they are **C3
  corporate-action-correct** — a split won't read as a crash).
- **DRY refactor (in-scope):** extract `objective_verdict`'s body
  (`postmortem.py:51`, `DEADZONE=1.0`) into a shared
  `direction_verdict(direction: str, fwd_pct: float | None, *, deadzone=1.0) -> str`
  in **`apps/market/returns.py`** — the neutral module both `thesis` and
  `predictions` already import for the forward-return itself, so "compute the
  return *and* classify it" co-locate (and it takes a plain `str` direction, so
  `returns.py` stays free of any model import). Both `PostMortem` and
  `AIPrediction` resolution call it; `objective_verdict(thesis, fwd)` becomes a
  thin wrapper (`return direction_verdict(thesis.direction, fwd)`) for back-compat.

## 5. Data model

`apps/predictions/models.py`:

```python
class AIPrediction(models.Model):
    # What was called
    ticker = models.CharField(max_length=16, db_index=True)
    direction = models.CharField(max_length=8)         # bullish | bearish | neutral
    horizon_days = models.PositiveIntegerField()
    confidence = models.FloatField()                   # 0..1, stated or signal-mean
    rationale = models.TextField(blank=True, default="")          # observation headline/summary
    invalidation_price = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    invalidation_note = models.CharField(max_length=300, blank=True, default="")  # from Signal.invalidation

    # Who/what made it  (provider/model known DIRECTLY — no thread attribution needed)
    provider = models.CharField(max_length=32, db_index=True)
    model = models.CharField(max_length=64, db_index=True)
    source_message = models.ForeignKey("threads.Message", null=True, on_delete=SET_NULL)
    source_snapshot = models.ForeignKey("snapshots.Snapshot", null=True, on_delete=SET_NULL)
    profile = models.ForeignKey("profiles.TradingProfile", null=True, on_delete=SET_NULL)

    # Lifecycle
    predicted_at = models.DateTimeField(db_index=True)
    resolve_at = models.DateTimeField(db_index=True)   # predicted_at + horizon (trading days)
    status = models.CharField(max_length=12, default="open")  # open|resolving|resolved|invalidated
    # Outcome (filled at resolution)
    forward_return_pct = models.FloatField(null=True, blank=True)
    verdict = models.CharField(max_length=12, blank=True, default="")  # correct|incorrect|mixed|inconclusive
    resolved_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [Index(fields=["ticker", "status"]),
                   Index(fields=["provider", "model", "status"]),
                   Index(fields=["status", "resolve_at"])]   # the beat-task scan
```

**Retention:** like `AIRun` / `PostMortem`, `AIPrediction` is **load-bearing
calibration substrate and is NEVER pruned** (the retention note in CLAUDE.md lists
the protected tables — add this one). Volume is bounded by observer fire-rate ×
the dedup rule (§6).

## 6. Features, phased

Each phase is independently shippable and adds visible value. **Phase 1 (F1–F4)
is the milestone's heart — it alone closes the AI's loop.** F5–F7 are separable
follow-ons.

### Phase 1 — the closed loop

**F1 — `AIPrediction` model + extraction (no new AI cost).**
Extraction is an **explicit call** (no Django signals — matches the repo
convention) at the end of the observer structured/consensus record functions
(`apps/observer/services/run.py:_run_structured_and_record` /
`_run_consensus_and_record`). When the report carries a directional call
(`predicted_direction` present, or the consensus `modal_bias`), create one
`AIPrediction`:
- `ticker` = snapshot `primary_ticker` (fallback: first `signals[].ticker`);
- `direction` = `predicted_direction` (consensus: `modal_bias` mapped, `mixed`→skip);
- `horizon_days` = `predicted_horizon_days` (fallback: a configured default, e.g. 7);
- `confidence` = `predicted_confidence` or `mean(signal.confidence)` (the schema's
  own documented fallback) — skip if neither exists;
- `invalidation_note` = the matching `Signal.invalidation`;
- `provider`/`model` from the fire; `source_*` FKs; `resolve_at` via
  `add_trading_days` (`apps/market/calendar`).

**Dedup rule (prevents an hourly observer from flooding the ledger):** at most
**one `open` prediction per `(ticker, horizon_days, profile)`**. A new fire on an
already-open call **updates** it (latest rationale/confidence, refreshed
`predicted_at`/`resolve_at`) unless the **direction flipped**, in which case the
prior open call is resolved-early as `invalidated` ("the AI changed its mind")
and a fresh one is created. This keeps each ledger row a meaningful, distinct
call. Zero added AI cost — pure reuse of the structured output already produced.

**F2 — auto-resolution + shared verdict.**
Beat task `predictions.resolve_due` (every 300s, mirroring
`thesis.run_due_postmortems`): for each `open` prediction with `resolve_at <=
now`, idempotently claim it (`filter(id=…, status="open").update(status="resolving")`;
0 rows ⇒ already claimed ⇒ skip), compute `forward_return_pct` via
`returns.forward_return_pct(ticker, predicted_at, resolve_at)` (C3-correct,
look-ahead-safe because `resolve_at = predicted_at + horizon` and we run at/after
it), set `verdict = direction_verdict(direction, fwd)`, stamp `resolved_at`,
`notify`. Predictions on tickers without price history resolve `inconclusive`
(null forward return) and are excluded from hit-rate/Brier — exactly like
post-mortems. **Deterministic; no AI key needed; fully testable without a model.**

**F3 — live AI calibration analytics + 3rd scorecard track.**
New `apps/analytics/services/ai_calibration.py` (sibling to `calibration.py`),
DRF view under `/api/analytics/ai-calibration/` + a drilldown mirroring
`calibration_drilldown` (C6). Aggregates resolved `AIPrediction`s by:
- **confidence band** (e.g. 0.5–0.6 … 0.9–1.0) with **Brier from the stated
  confidence directly** (`(confidence − outcome)²` — cleaner than the thesis
  conviction→prob map, because the AI states probability);
- **`(provider, model)`** — a direct group-by (the provider is on the row; no
  thread attribution needed, unlike the thesis provider section);
- **direction** and **horizon**.
Surfaces as a **third track on `/scorecard`**: *trader thesis calibration* |
*offline eval calibration* (existing) | **live AI prediction calibration** (new),
with the same clickable drilldown to the underlying predictions. The triangulation
(§2.3) is the headline.

**F4 — coach injects the AI's OWN live track record.**
New `apps/threads/coach.py:_ai_track_record_block(ticker, profile)` (lazy-imports
`predictions`): from **resolved** predictions only (never open — no leakage),
render e.g.

> ### My own recent calls here
> - On $NVDA, my last 8 resolved calls: 5 correct (63%). I've run **over-confident**
>   on bullish 7-day calls (stated 0.78, realized 0.50) — discount accordingly.

Wired into **both** `assemble_coach_context` (snapshot path) **and**
`assemble_coach_context_for_message` (the A2 snapshot-free path) as one more
`_safe(...)` sub-block, riding the existing **`enable_coach`** per-profile gate.
This is the loop-closing payload: the model sees its real-world accuracy at
generation time. It is the **same proven pattern** as the M7/A3 `_calibration_block`
(which already injects *offline* eval calibration) — F4 adds the *live* counterpart.

### Phase 2 — early-warning

**F5 — prediction-invalidation alerts.**
Beat task `predictions.check_invalidations` (every ~5 min, or piggyback the
existing trigger tick): for `open` predictions with an `invalidation_price`, if
the current price (via `returns.nearest_bar_close`) has breached it before
`resolve_at`, mark `invalidated` + `notify` ("The AI's bullish $NVDA call from 3d
ago is being invalidated — broke below $X"). Low-noise by construction (fires only
for predictions that carry an explicit price level, a minority). Default-on but
cheap; no AI calls.

### Phase 3 — the loop acts

**F6 — calibration-weighted provider routing (opt-in).**
`apps/ai/router.py` gains an optional selection step: when
`AI_CALIBRATION_ROUTING_ENABLED`, the default `(provider, model)` for a run is
chosen by blending the **offline `EvalRun`** calibration and the **live
`AIPrediction`** calibration (recency-weighted), preferring the best-calibrated
for the situation (ticker/direction/horizon slice when it has ≥ N samples, else
the global figure). **Honest fallback** to the configured default when data is
thin. This is the eval loop finally *acting* on its own measurements — the
capstone of the self-correcting thesis. Opt-in because it changes selection (a
real behavior change), consistent with `AI_FAILOVER_ENABLED` et al.

**F7 — thesis ↔ prediction reconciliation (stretch).**
Where a trader `Thesis` and an `AIPrediction` both exist on a ticker, surface
agreement/divergence on the thesis detail page / a dashboard tile: "You: bullish
conv-4. AI: neutral 7d — divergence; the AI flagged X." Pure read-side join over
existing data. Stretch; cut first under time pressure.

## 7. Look-ahead safety & feedback-loop risk

- **No look-ahead.** Resolution reads price over `[predicted_at, resolve_at]` and
  runs at/after `resolve_at`; identical to the post-mortem guarantee. The coach's
  F4 block reads **only resolved** predictions (verdict known, horizon elapsed),
  so it can never feed a not-yet-resolved call back into generation.
- **Self-reinforcement.** Injecting the AI's own track record could in principle
  cause over-correction oscillation. Mitigation: F4 is **informational
  calibration only** (a hit-rate + an over/under verdict), the *same* shape as the
  already-shipped offline `_calibration_block` (A3) — a proven, bounded pattern,
  not a new risk class. We will note it and watch the live-vs-offline divergence
  (§2.3) as the canary.
- **Sparsity.** Predictions flow only from **structured/consensus** fires (Phase
  1's zero-cost source). A user running only free-form observers gets an empty
  ledger. Accepted: structured mode is the recommended config and is more useful
  anyway. An opt-in *plain-fire extraction pass* (a cheap structured second call
  on free-form fires, behind `PREDICTION_EXTRACTION_ENABLED`) is a documented
  **future extension**, not Phase 1 — keeps the core free of new AI cost.
- **Dedup honesty.** The §6 one-open-call-per-`(ticker,horizon,profile)` rule
  stops quiet-period flooding from over-weighting calibration; a direction flip
  is recorded as an early `invalidated` so the ledger tells the real story.

## 8. Opt-in matrix (per the repo's default-off-for-behavior-changes convention)

| Behavior | Default | Flag | Rationale |
|---|---|---|---|
| Extract predictions from structured/consensus fires | **ON** | — | Core loop; zero added AI cost; avoids the "built-but-hidden" anti-pattern |
| Auto-resolve + scorecard track | **ON** | — | Deterministic, cheap, the visible payoff |
| Coach AI-track-record block (F4) | per-profile | existing `enable_coach` | Changes the live prompt → rides the established coach gate |
| Invalidation alerts (F5) | **ON** | — | Low-noise (price-level-only); a notification, not a cost |
| Plain-fire extraction pass | OFF | `PREDICTION_EXTRACTION_ENABLED` | Adds an AI call per free-form fire |
| Calibration-weighted routing (F6) | OFF | `AI_CALIBRATION_ROUTING_ENABLED` | Changes provider selection — a real behavior change |

**Deliberate stance:** the *ledger itself* (data + resolution + scorecard) is
**on by default** so it is visible, not inert — directly heeding the
`product-improvement-audit` lesson that this codebase's recurring failure mode is
*built-but-hidden capability*. Only the parts that change the live prompt, add AI
cost, or alter selection are gated.

## 9. Testing strategy

- **Unit (no AI):** `extract_prediction` over canned `ObservationReport`s
  (directional call present/absent, signal-mean fallback, dedup-update vs
  direction-flip-invalidate); `direction_verdict` truth table (shared with the
  post-mortem tests — parametrized); `resolve_due` idempotent claim (overlap is a
  no-op); look-ahead safety (resolve uses `[predicted_at, resolve_at]`); C3 split
  in the window resolves flat, not crashed.
- **Analytics:** `ai_prediction_calibration` buckets/Brier reconcile with the
  drilldown counts (same population), mirroring the C6 reconciliation test.
- **Coach:** `_ai_track_record_block` renders from resolved-only predictions,
  empty when none, gated on `enable_coach`; integrates into both coach entry
  points (extends the A2 + existing coach test suites).
- **Routing (F6):** calibration-weighted selection prefers the better-calibrated
  pair when data is sufficient and **falls back honestly** when thin.
- All resolution/extraction is deterministic → no `MOCK_EXTERNAL`/model needed
  (the structured report is patched directly, as the M7/observer tests already do).

## 10. Milestone sequencing

1. **Phase 1 (F1–F4)** — model + migration; shared `direction_verdict` extract;
   extraction hook; `resolve_due` beat; `ai_calibration` service + view +
   scorecard track + drilldown; coach block. *Ships the closed loop.*
2. **Phase 2 (F5)** — invalidation watch + alert.
3. **Phase 3 (F6, + F7 stretch)** — calibration-weighted routing; reconciliation.

Each phase = its own plan + PR, bite-sized commits, `make check` gating — the
repo's established cadence.

## 11. Open questions for the user (non-blocking — sound defaults chosen above)

1. **Theme:** confirmed direction = the Prediction Ledger? (Alternatives C/D/E in
   §3 remain available as *later* milestones that hang off it.)
2. **Default horizon** when `predicted_horizon_days` is null — 7 trading days
   proposed. Reasonable, or prefer the profile's typical holding period?
3. **F6 routing appetite:** include calibration-weighted routing in M13 (Phase
   3), or split it into its own follow-up milestone once the live signal has
   accrued a few weeks of data? (Routing on a thin ledger is unwise; I lean
   "ship F1–F5 first, F6 as a fast-follow.")
4. **Plain-fire extraction:** is the structured-fires-only source acceptable for
   v1 (recommended), or is populating the ledger from free-form fires important
   enough to include the opt-in extraction pass now?

## 12. Out of scope (YAGNI)

Narrative/regime tracking (C), scenario trees (D), new asset classes (E),
prediction extraction from ad-hoc chat threads, a bespoke predictions UI beyond
the scorecard track + reconciliation tile, and any change to how *trader* theses
work. The ledger is about the **AI's** forecasts; the trader's loop is already
closed.
