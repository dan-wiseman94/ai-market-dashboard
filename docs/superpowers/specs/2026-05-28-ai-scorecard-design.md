# AI Calibration Scorecard (`/scorecard`) — design

**Date:** 2026-05-28
**Status:** Approved (pending spec review)
**Topic:** A calibration scorecard answering "should I trust the AI / my own conviction, historically?" — thesis-conviction calibration (hit-rate by conviction bucket, Brier, calibration curve) + provider calibration (per-provider thesis hit-rate), on a dedicated `/scorecard` page. Feature #3 of the roadmap; independent of the events + briefing features.

## Problem

The dashboard accumulates directional calls (`Thesis`, with a 1–5 `conviction`) and closes the loop on them deterministically (`PostMortem.verdict` ∈ correct/incorrect/mixed/inconclusive, computed by `objective_verdict()` from the actual forward return). But nothing surfaces the **meta-signal**: *are my conviction levels calibrated to outcomes?* Does a conviction-5 thesis actually resolve "correct" more often than a conviction-2 one? And *which AI provider's consults led to theses that panned out?* The existing provider leaderboard correlates AI runs to raw forward returns, but never frames it as calibration, and never connects conviction → realized hit-rate.

This is feature #3 of the roadmap. It's pure aggregation over data that already exists (`PostMortem ⋈ Thesis`, and `Thesis → source thread → AIRun.provider`) — no AI key, no new capture, no scheduled task. It follows the established `apps.analytics` pattern (a service + a DRF view + a `use*` hook), but surfaces on its own page rather than as a 6th card, because the calibration curve + two tables want room.

## Non-goals (YAGNI)

- **Time-series calibration trends** (calibration drift over time). v1 is a point-in-time snapshot over a window.
- **Per-model Brier / confidence intervals.** Brier is computed at the overall thesis level; provider calibration is provider+model hit-rate without CIs.
- **Manual-close outcomes as a calibration source.** We use only the deterministic `PostMortem.verdict` (objective, from forward return) — not the user's manual `closed_win/closed_loss` status (subject to close-timing bias).
- **Duplicating the leaderboard's forward-return table.** Provider calibration is verdict-grounded hit-rate; the page links to the existing leaderboard for raw return correlation.
- **A scheduled task / stored aggregates.** On-demand at request time, like all of `apps.analytics`.

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| What it scores | Both: thesis-conviction calibration + provider calibration | Chosen during brainstorming; the provider half is verdict-grounded (not the fuzzier return angle) |
| Outcome source | `PostMortem.verdict` (deterministic) | Objective, key-free, already computed; mixed/inconclusive shown but excluded from hit-rate/Brier |
| Horizon handling | `?horizon=` ∈ {7,30,90}, default 30; one PostMortem per thesis | Each thesis has up to 3 PMs (7/30/90d); selecting a horizon avoids triple-counting |
| Brier probability mapping | `p = 0.5 + (conviction−1)/4 × 0.4` → 0.5…0.9 | Conviction has no native probability; a documented linear map, returned in the payload so it's visible/tunable |
| Provider calibration metric | Per-(provider,model) hit-rate of post-mortem'd theses whose source thread used that provider | Verdict-grounded + non-redundant with the leaderboard; honest coverage |
| Surface | Dedicated `/scorecard` page (not a 6th `/analytics` card) | The calibration curve + two tables want room; chosen during brainstorming |
| Storage / scheduling | None — on-demand service | Matches all 5 existing analytics |

## Architecture

One service computing both sections, one endpoint, one page. No new models, no migration.

```
PostMortem (status=done, horizon=H, verdict, forward_return_pct)  ⋈  Thesis (conviction, direction, thread)
        │                                                                      │
        ▼  thesis calibration                                                  ▼  provider calibration
  bucket by conviction 1-5 → hit_rate                              Thesis.thread → AIRun(message__thread).provider
  calibration curve + Brier + overall                             group verdicts by provider → per-provider hit_rate
        └──────────────────────────────┬───────────────────────────────────────┘
                                        ▼
              calibration(start, end, horizon) → {"thesis": {...}, "provider": [...], ...}
                                        ▼
                      GET /api/analytics/calibration/   ◀── /scorecard page (curve + tables, horizon selector)
```

### 1. Service — `apps/analytics/services/calibration.py`

`calibration(*, start, end, horizon) -> dict`. Window filters on `PostMortem.completed_at` within `[start, end)` (post-mortems lag thesis open by 7–90d, so the view defaults to a 90-day window).

**Eligible rows:** `PostMortem.objects.filter(status="done", horizon_days=horizon, completed_at__gte=start, completed_at__lt=end, forward_return_pct__isnull=False).select_related("thesis")`. One PostMortem per thesis at the chosen horizon → each thesis contributes once.

**Thesis calibration** (`"thesis"` section):
- `buckets`: list keyed by `conviction` 1–5, each `{conviction, n, correct, incorrect, mixed, inconclusive, hit_rate}` where `hit_rate = correct/(correct+incorrect)` (None when the denominator is 0). This list *is* the calibration curve.
- `brier`: over rows with verdict ∈ {correct, incorrect}, `p = round(0.5 + (conviction-1)/4 * 0.4, 4)`, `o = 1.0 if correct else 0.0`, `brier = mean((p-o)**2)` (None when no scorable rows). `prob_map` (the conviction→p table) is returned alongside.
- `overall`: `{scored, hit_rate, correct, incorrect, mixed, inconclusive, avg_forward_return_pct}`.
- `by_direction`: `{bullish|bearish|neutral: {n, hit_rate}}`.

**Provider calibration** (`"provider"` section): for each eligible thesis with a `thread`, collect the distinct `(provider, model)` from that thread's done AIRuns (`AIRun.objects.filter(message__thread_id=thesis.thread_id, status="done").values_list("provider","model").distinct()`); attribute the thesis's verdict to each. Group → list of `{provider, model, n, correct, incorrect, hit_rate}` ordered by `n` desc. `attributable` = count of scored theses with ≥1 attributable provider (coverage honesty).

All math degrades to zeros/None on empty input — never divides by zero, never raises.

### 2. API — `apps/analytics/views.py` + `urls.py`

`CalibrationView(APIView)` mirroring `LeaderboardView`: reuse `_parse_range(request, default_days=90)`; `horizon = int(query_params.get("horizon","30"))` clamped to {7,30,90} (invalid → 30). Returns `{start, end, horizon, **calibration(...)}`. Route `path("calibration/", CalibrationView.as_view(), name="analytics-calibration")` added to `apps/analytics/urls.py`.

### 3. Frontend — dedicated `/scorecard` page

- **Hook** `useCalibration(days, horizon)` in `frontend/src/hooks/useAnalytics.ts` (mirrors `useLeaderboard`), queryKey `["analytics/calibration", days, horizon]`.
- **Page** `frontend/src/pages/ScorecardPage.tsx`:
  - **Thesis calibration** section: an overall stat row (hit-rate · Brier · n scored); a horizon selector (7/30/90); a calibration table — one row per conviction bucket showing `n` and `hit_rate` (a simple inline bar visualizes hit_rate, no chart lib needed); the by-direction mini-breakdown.
  - **Provider calibration** section: a table (provider/model · n · hit-rate), with a coverage line ("M of N scored theses were attributable to a provider") and a link to `/analytics` for raw return correlation.
  - Loading → `Skeleton`/`SkeletonRows`; empty/low-sample → `EmptyState` ("N scored theses — calibration sharpens as more theses post-mortem").
- **Wiring:** route `{ path: "scorecard", element: <ScorecardPage/>, handle: { crumb: "Scorecard" } }`; SideNav entry in the **SYSTEM** group near Analytics (`["/scorecard", "Scorecard", "SC"]`); `go-scorecard` Cmd-K command (`keywords: "calibration brier conviction hit rate trust"`); **`g k`** keyboard shortcut (free — taken: d/s/t/h/c/o/a/j/e/b).

### 4. Testing

- **Service** (`apps/analytics/tests/test_calibration.py`): bucket hit-rate math (seed theses+PMs at fixed convictions/verdicts); Brier with a known mapping + known outcomes; horizon selection (a thesis with 7/30/90 PMs counts once at the chosen horizon); mixed/inconclusive excluded from hit-rate/Brier but counted; provider attribution via source-thread AIRuns (incl. multi-provider thread → counts for each); empty input → zeros/None, no crash/zero-division; `by_direction` split.
- **API** (`test_calibration.py` API portion or same file): range + horizon clamp (invalid horizon → 30); response shape.
- **Frontend** (`vitest`): `useCalibration` hook; `ScorecardPage` render (loading/empty/populated, horizon switch).

## Implementation order (for the plan)

1. `calibration()` service — thesis section (buckets/curve/Brier/overall/by_direction) + tests.
2. `calibration()` service — provider section (source-thread attribution) + tests.
3. `CalibrationView` + route + contract test.
4. Frontend: `useCalibration` hook + test.
5. Frontend: `ScorecardPage` + route/nav/command/`g k` + render test.
6. Full check + docs (CLAUDE.md note + roadmap milestone pointer).

Steps 3–5 depend on 1–2; the page (5) depends on the hook (4).
