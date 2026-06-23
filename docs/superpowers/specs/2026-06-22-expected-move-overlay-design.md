# Expected-Move Overlay — Design

**Written 2026-06-22.** Feature #13 from the 2026-06-22 deep review. Frame every
observation/prediction against the **options-implied move**: feed the AI what the
options market priced, and score whether reality beat the straddle.

## Decisions (brainstormed)
- **Primary job:** both *feed the AI* AND *score predictions* (full framing).
- **Horizon basis:** a small **term structure** at the standard horizons (7/30/90d)
  for the AI feed; for scoring, freeze the expected move at the prediction's own
  `horizon_days`. Apples-to-apples (actual move vs priced move over the same horizon).
- **Readout:** Prediction Ledger + Scorecard ("beat-the-straddle" rate).
- **Convention:** 1σ (~68%), `move = atm_iv × √(days/365)`. Nearest-expiry ATM IV,
  no interpolation. One nullable column on `AIPrediction` (no new table).

## 1. Deterministic calc — `apps/market/services/expected_move.py`
Pure, defensive (never raises; `None`/`[]` on missing data).
- `one_sigma_pct(atm_iv: float, horizon_days: int) -> float` — `atm_iv × sqrt(days/365)`,
  the 1σ move as a fraction. **IV normalization:** Schwab's `volatility` field arrives
  as a percent (`25.0`), so divide by 100 when `atm_iv > 3.0` (a 300%+ decimal IV is
  not real; this disambiguates 0.25 vs 25.0 safely).
- `term_structure(chain_payload, *, horizons=(7,30,90), spot=None) -> list[dict]` —
  reuses `option_analytics.chain_analytics(...)["term_structure"]` (already
  `[{expiry, atm_iv}]`). For each horizon, pick the expiry whose days-to-expiration is
  **nearest** the horizon; emit `{horizon_days, atm_iv, move_pct, move_abs}`
  (`move_abs = spot × move_pct` when spot known). `[]` on no chain / no IV.
- `for_horizon(chain_payload, horizon_days, *, spot=None) -> float | None` — the single
  `move_pct` for one horizon (used by the prediction freeze).

DTE is computed from the expiry date string vs `today`. Helpers stay module-private.

## 2. Feed the AI (deterministic, $0)
In `apps/snapshots/serializer.py::_render_chain`, append one line built from
`term_structure(payload, spot=underlying_last)`:
`Options-implied move (1σ): ±2.1% (7d) · ±4.3% (30d) · ±7.5% (90d)`.
Omitted entirely when the term structure is empty. No AI cost, no new section — it
rides the existing chain section the model already sees.

## 3. Freeze on the prediction
- **Migration:** add `expected_move_pct = models.FloatField(null=True, blank=True)` to
  `apps.observer.AIPrediction` (`db_table` preserved; additive, reversible).
- **Extraction:** `observer/predictions/services/extract.py` — when a prediction with
  `horizon_days=H` is created, compute `expected_move_pct = for_horizon(chain, H)` from
  the **observation's snapshot** OptionChainSnapshot for the primary ticker. `None` when
  no chain. Best-effort — a calc failure must NEVER break extraction (mirrors the
  existing "None never breaks the fire" rule). Frozen at decision time = honest
  (the priced move when the call was made, like the rest of the look-ahead-safe ledger).

## 4. Score at resolution (derived, no new field)
`AIPrediction` already stores `forward_return_pct` + `verdict` at resolution. The
comparison is **derived** wherever read:
`move_beyond_priced = abs(forward_return_pct) > expected_move_pct` (both present).
`move_vs_priced ∈ {"within","beyond", None}`.

## 5. Readout — Prediction Ledger + Scorecard
- **Ledger API:** the `AIPrediction` serializer gains `expected_move_pct` and a derived
  `move_vs_priced`. FE prediction-ledger rows show `priced ±X% · actual Y% → beyond/within`.
- **Scorecard:** new analytics aggregation `beat_the_straddle(horizon)` over resolved
  predictions that have an `expected_move_pct` and a `forward_return_pct`:
  - `n`, `beyond_rate` (share where `|actual| > priced`),
  - `edge_rate` (share that were **directionally correct AND beyond priced** — the
    strongest cell), `within_rate`. `inconclusive`/no-IV excluded (honest min-n, like
    the rest of the scorecard). A Scorecard card renders it; one
    `django_assert_max_num_queries` budget test pins the query count.

## 6. Testing
- Calc: parametrized `one_sigma_pct` (IV/horizon → move), percent-normalization
  (25.0 vs 0.25), nearest-expiry selection, defensive `None`/`[]`.
- Serializer: chain render includes the expected-move line when IV present; omitted when not.
- Extraction: a prediction off a snapshot with a chain freezes `expected_move_pct`;
  no-chain → `None`, extraction still succeeds.
- Scorecard: `beat_the_straddle` aggregation hand-checkable + N+1 budget.
- FE: ledger row shows the priced/actual badge; scorecard card renders the rate; vitest.

## Out of scope (YAGNI)
2σ bands, IV interpolation across expiries, a snapshot UI badge, a new beat task,
back-filling `expected_move_pct` on historical predictions (forward-only; old rows stay `None`).
