# AI Calibration Scorecard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A calibration scorecard — thesis-conviction calibration (hit-rate by conviction bucket, Brier, curve) + provider calibration (per-provider thesis hit-rate) — on a dedicated `/scorecard` page.

**Architecture:** One on-demand `apps/analytics/services/calibration.py` service aggregating `PostMortem ⋈ Thesis` (+ `Thesis → source thread → AIRun.provider`) → a single `GET /api/analytics/calibration/` endpoint → a dedicated `/scorecard` React page. No new models/migrations; follows the existing analytics pattern (service + APIView + `use*` hook).

**Tech Stack:** Django + DRF, Postgres; React 18 + TS, TanStack Query.

**Spec:** `docs/superpowers/specs/2026-05-28-ai-scorecard-design.md`

**Base:** `feat/ai-scorecard` off `origin/main` (independent — #20 + #21 already merged; no stacking).

---

## Conventions for this plan
- Work on branch `feat/ai-scorecard` (already checked out). **GUARDRAIL: do NOT run `git pull`/`fetch`/`merge`/`rebase`/`checkout <branch>`; stay on this branch; only `git add <specific files>` + commit.**
- Backend tests in-container, drop `backend/` prefix: `docker compose exec -T web pytest apps/analytics/tests/test_calibration.py -v`
- Frontend: `docker compose exec -T frontend pnpm exec vitest run <path>` · `... tsc --noEmit` · `... pnpm run lint`
- TDD: failing test → run fail → implement → run pass → commit.
- Stage ONLY listed files (never `git add -A`; NEVER stage `e2e/visual/__screenshots__/`).
- Commits end with `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`. Prefix `LEFTHOOK=0` if the hook errors. `ty` is advisory.

## File structure
- Create: `backend/apps/analytics/services/calibration.py`, `backend/apps/analytics/tests/test_calibration.py`, `frontend/src/pages/ScorecardPage.tsx`, `frontend/src/__tests__/ScorecardPage.test.tsx`, `frontend/src/__tests__/hooks/useCalibration.test.tsx`.
- Modify: `backend/apps/analytics/views.py`, `backend/apps/analytics/urls.py`, `frontend/src/hooks/useAnalytics.ts`, `frontend/src/router.tsx`, `frontend/src/components/layout/SideNav.tsx`, `frontend/src/components/layout/AppLayout.tsx`, `frontend/src/hooks/useKeyboardShortcuts.ts`, `CLAUDE.md`, `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`.

---

### Task 1: `calibration()` service (thesis + provider)

**Files:** Create `backend/apps/analytics/services/calibration.py`, `backend/apps/analytics/tests/test_calibration.py`.

- [ ] **Step 1: Write the failing tests** — create `backend/apps/analytics/tests/test_calibration.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from apps.analytics.services.calibration import _prob_for_conviction, calibration
from apps.profiles.models import TradingProfile
from apps.thesis.models import PostMortem, Thesis
from apps.threads.models import AIRun, Message, Thread

NOW = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
WIN = (NOW - timedelta(days=90), NOW + timedelta(days=1))


@pytest.fixture
def profile(db):
    return TradingProfile.objects.create(name="p", style="s")


def _thesis(conviction: int, direction: str = "bullish", thread=None) -> Thesis:
    return Thesis.objects.create(
        title="t", ticker="NVDA", direction=direction, conviction=conviction,
        status="closed_win", thread=thread,
    )


def _pm(thesis: Thesis, *, horizon: int, verdict: str, fwd: float | None,
        completed: datetime = NOW) -> PostMortem:
    return PostMortem.objects.create(
        thesis=thesis, horizon_days=horizon, due_at=completed, status="done",
        verdict=verdict, forward_return_pct=fwd, completed_at=completed,
    )


def test_prob_for_conviction_maps_1_to_0_5_and_5_to_0_9():
    assert _prob_for_conviction(1) == 0.5
    assert _prob_for_conviction(3) == 0.7
    assert _prob_for_conviction(5) == 0.9


@pytest.mark.django_db
def test_thesis_buckets_and_overall_hitrate(profile):
    _pm(_thesis(5), horizon=30, verdict="correct", fwd=8.0)
    _pm(_thesis(5), horizon=30, verdict="incorrect", fwd=-3.0)
    _pm(_thesis(2), horizon=30, verdict="correct", fwd=2.0)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    th = out["thesis"]
    b5 = next(b for b in th["buckets"] if b["conviction"] == 5)
    assert b5["n"] == 2 and b5["correct"] == 1 and b5["incorrect"] == 1
    assert b5["hit_rate"] == 0.5
    assert th["overall"]["scored"] == 3
    assert th["overall"]["hit_rate"] == round(2 / 3, 4)


@pytest.mark.django_db
def test_brier_known_value(profile):
    # conviction 5 (p=0.9) correct -> (0.9-1)^2=0.01 ; conviction 1 (p=0.5) incorrect -> 0.25
    _pm(_thesis(5), horizon=30, verdict="correct", fwd=5.0)
    _pm(_thesis(1), horizon=30, verdict="incorrect", fwd=-5.0)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    assert out["thesis"]["brier"] == round((0.01 + 0.25) / 2, 4)


@pytest.mark.django_db
def test_horizon_selects_one_pm_per_thesis(profile):
    t = _thesis(4)
    _pm(t, horizon=7, verdict="incorrect", fwd=-1.0)
    _pm(t, horizon=30, verdict="correct", fwd=6.0)
    _pm(t, horizon=90, verdict="correct", fwd=9.0)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    assert out["thesis"]["overall"]["scored"] == 1
    assert out["thesis"]["overall"]["correct"] == 1


@pytest.mark.django_db
def test_mixed_inconclusive_counted_but_excluded_from_hitrate(profile):
    _pm(_thesis(3), horizon=30, verdict="mixed", fwd=0.5)
    _pm(_thesis(3), horizon=30, verdict="inconclusive", fwd=0.2)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    ov = out["thesis"]["overall"]
    assert ov["mixed"] == 1 and ov["inconclusive"] == 1
    assert ov["hit_rate"] is None  # no correct/incorrect → undefined


@pytest.mark.django_db
def test_provider_attribution_via_source_thread(profile):
    thread = Thread.objects.create(kind="consult", profile=profile)
    msg = Message.objects.create(thread=thread, role="assistant", content={"text": ""}, status="done")
    AIRun.objects.create(message=msg, provider="claude", model="claude-opus-4-8",
                         cost_usd=Decimal("0.1"), latency_ms=1000, status="done")
    _pm(_thesis(5, thread=thread), horizon=30, verdict="correct", fwd=7.0)
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    assert out["attributable"] == 1
    row = next(r for r in out["provider"] if r["provider"] == "claude")
    assert row["n"] == 1 and row["correct"] == 1 and row["hit_rate"] == 1.0


@pytest.mark.django_db
def test_empty_input_returns_zeros_no_crash(profile):
    out = calibration(start=WIN[0], end=WIN[1], horizon=30)
    assert out["thesis"]["overall"]["scored"] == 0
    assert out["thesis"]["brier"] is None
    assert out["thesis"]["overall"]["hit_rate"] is None
    assert out["provider"] == [] and out["attributable"] == 0
    assert len(out["thesis"]["buckets"]) == 5
```

- [ ] **Step 2: Run to verify it fails**
`docker compose exec -T web pytest apps/analytics/tests/test_calibration.py -v` → ImportError (module missing).

- [ ] **Step 3: Implement** — create `backend/apps/analytics/services/calibration.py`:

```python
"""Calibration scorecard: thesis conviction-vs-outcome + provider hit-rate.

On-demand aggregation over PostMortem ⋈ Thesis (and Thesis → source thread →
AIRun.provider). No AI key, no scheduled task — like the other analytics.
"""

from __future__ import annotations

from datetime import datetime

VALID_HORIZONS = (7, 30, 90)
_DECISIVE = ("correct", "incorrect")
_ALL_VERDICTS = ("correct", "incorrect", "mixed", "inconclusive")


def _prob_for_conviction(conviction: int) -> float:
    """Linear map conviction 1..5 -> implied probability 0.5..0.9 (documented, returned in payload)."""
    c = max(1, min(5, int(conviction)))
    return round(0.5 + (c - 1) / 4 * 0.4, 4)


PROB_MAP = {c: _prob_for_conviction(c) for c in range(1, 6)}


def _hit_rate(correct: int, incorrect: int) -> float | None:
    den = correct + incorrect
    return round(correct / den, 4) if den else None


def _thesis_section(rows: list[tuple[int, str, str, float | None]]) -> dict:
    buckets = {
        c: {"conviction": c, "n": 0, "correct": 0, "incorrect": 0,
            "mixed": 0, "inconclusive": 0, "hit_rate": None}
        for c in range(1, 6)
    }
    by_dir: dict[str, dict] = {}
    tot = {"scored": 0, "correct": 0, "incorrect": 0, "mixed": 0, "inconclusive": 0}
    brier_terms: list[float] = []
    ret_sum, ret_n = 0.0, 0

    for conviction, direction, verdict, fwd in rows:
        c = max(1, min(5, int(conviction)))
        b = buckets[c]
        b["n"] += 1
        tot["scored"] += 1
        if verdict in _ALL_VERDICTS:
            b[verdict] += 1
            tot[verdict] += 1
        d = by_dir.setdefault(direction, {"n": 0, "correct": 0, "incorrect": 0})
        d["n"] += 1
        if verdict in _DECISIVE:
            d[verdict] += 1
            o = 1.0 if verdict == "correct" else 0.0
            brier_terms.append((_prob_for_conviction(c) - o) ** 2)
        if fwd is not None:
            ret_sum += float(fwd)
            ret_n += 1

    for b in buckets.values():
        b["hit_rate"] = _hit_rate(b["correct"], b["incorrect"])

    return {
        "buckets": [buckets[c] for c in range(1, 6)],
        "brier": round(sum(brier_terms) / len(brier_terms), 4) if brier_terms else None,
        "prob_map": PROB_MAP,
        "overall": {
            "scored": tot["scored"],
            "hit_rate": _hit_rate(tot["correct"], tot["incorrect"]),
            "correct": tot["correct"], "incorrect": tot["incorrect"],
            "mixed": tot["mixed"], "inconclusive": tot["inconclusive"],
            "avg_forward_return_pct": round(ret_sum / ret_n, 4) if ret_n else None,
        },
        "by_direction": {
            d: {"n": v["n"], "hit_rate": _hit_rate(v["correct"], v["incorrect"])}
            for d, v in by_dir.items()
        },
    }


def _provider_section(pms) -> tuple[list[dict], int]:
    from apps.threads.models import AIRun

    agg: dict[tuple[str, str], dict] = {}
    attributable = 0
    for pm in pms:
        thread_id = pm.thesis.thread_id
        if not thread_id:
            continue
        pairs = list(
            AIRun.objects.filter(message__thread_id=thread_id, status="done")
            .values_list("provider", "model")
            .distinct()
        )
        if not pairs:
            continue
        attributable += 1
        for provider, model in pairs:
            a = agg.setdefault(
                (provider, model),
                {"provider": provider, "model": model, "n": 0, "correct": 0, "incorrect": 0},
            )
            a["n"] += 1
            if pm.verdict in _DECISIVE:
                a[pm.verdict] += 1
    rows = []
    for a in agg.values():
        a["hit_rate"] = _hit_rate(a["correct"], a["incorrect"])
        rows.append(a)
    rows.sort(key=lambda r: r["n"], reverse=True)
    return rows, attributable


def calibration(*, start: datetime, end: datetime, horizon: int = 30) -> dict:
    from apps.thesis.models import PostMortem

    horizon = horizon if horizon in VALID_HORIZONS else 30
    pms = list(
        PostMortem.objects.filter(
            status="done",
            horizon_days=horizon,
            completed_at__gte=start,
            completed_at__lt=end,
            forward_return_pct__isnull=False,
        ).select_related("thesis")
    )
    thesis_rows = [
        (pm.thesis.conviction, pm.thesis.direction, pm.verdict, pm.forward_return_pct)
        for pm in pms
    ]
    thesis = _thesis_section(thesis_rows)
    provider, attributable = _provider_section(pms)
    return {
        "horizon": horizon,
        "scored": thesis["overall"]["scored"],
        "attributable": attributable,
        "thesis": thesis,
        "provider": provider,
    }
```

- [ ] **Step 4: Run to verify pass**
`docker compose exec -T web pytest apps/analytics/tests/test_calibration.py -v` → all 7 pass.

- [ ] **Step 5: Commit**
```bash
git add backend/apps/analytics/services/calibration.py backend/apps/analytics/tests/test_calibration.py
LEFTHOOK=0 git commit -m "feat(analytics): calibration service (thesis + provider hit-rate)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `GET /api/analytics/calibration/` endpoint

**Files:** Modify `backend/apps/analytics/views.py`, `backend/apps/analytics/urls.py`; Create `backend/apps/analytics/tests/test_calibration_endpoint.py`.

- [ ] **Step 1: Write the failing test** — create `backend/apps/analytics/tests/test_calibration_endpoint.py`:

```python
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_calibration_endpoint_shape(api):
    r = api.get("/api/analytics/calibration/")
    assert r.status_code == 200
    body = r.json()
    assert body["horizon"] == 30
    assert "thesis" in body and "provider" in body
    assert len(body["thesis"]["buckets"]) == 5


@pytest.mark.django_db
def test_calibration_endpoint_clamps_invalid_horizon(api):
    assert api.get("/api/analytics/calibration/?horizon=999").json()["horizon"] == 30
    assert api.get("/api/analytics/calibration/?horizon=7").json()["horizon"] == 7
```

- [ ] **Step 2: Run to verify it fails**
`docker compose exec -T web pytest apps/analytics/tests/test_calibration_endpoint.py -v` → 404.

- [ ] **Step 3: Implement**

Append to `backend/apps/analytics/views.py` (the `_parse_range` helper + `APIView`/`Request`/`Response` imports already exist at the top):

```python
class CalibrationView(APIView):
    def get(self, request: Request) -> Response:
        from apps.analytics.services.calibration import calibration

        start, end = _parse_range(request, default_days=90)
        try:
            horizon = int(request.query_params.get("horizon", "30"))
        except ValueError:
            horizon = 30
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                **calibration(start=start, end=end, horizon=horizon),
            }
        )
```

In `backend/apps/analytics/urls.py`: add `CalibrationView` to the `from apps.analytics.views import (...)` block, and add to `urlpatterns`:
```python
    path("calibration/", CalibrationView.as_view(), name="analytics-calibration"),
```

- [ ] **Step 4: Run to verify pass + regression**
```bash
docker compose exec -T web pytest apps/analytics/tests/test_calibration_endpoint.py -v
docker compose exec -T web pytest apps/analytics -q
```
Expected: 2 new pass; full analytics suite passes (existing endpoints intact). (The service clamps the horizon, so the view passing an out-of-range int still yields 30.)

- [ ] **Step 5: Commit**
```bash
git add backend/apps/analytics/views.py backend/apps/analytics/urls.py \
        backend/apps/analytics/tests/test_calibration_endpoint.py
LEFTHOOK=0 git commit -m "feat(analytics): GET /api/analytics/calibration/ endpoint

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Frontend `useCalibration` hook

**Files:** Modify `frontend/src/hooks/useAnalytics.ts`; Create `frontend/src/__tests__/hooks/useCalibration.test.tsx`.

- [ ] **Step 1: Write the failing test** — create `frontend/src/__tests__/hooks/useCalibration.test.tsx`:

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as client from "@/api/client";
import { useCalibration } from "@/hooks/useAnalytics";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useCalibration", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("fetches calibration for the horizon", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue({
      horizon: 30, scored: 1, attributable: 0,
      thesis: { buckets: [], brier: 0.1, prob_map: {}, overall: { scored: 1, hit_rate: 1, correct: 1, incorrect: 0, mixed: 0, inconclusive: 0, avg_forward_return_pct: 5 }, by_direction: {} },
      provider: [],
    });
    const { result } = renderHook(() => useCalibration(90, 30), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.horizon).toBe(30);
    expect(spy).toHaveBeenCalledWith(expect.stringContaining("/api/analytics/calibration/?horizon=30"));
  });
});
```

- [ ] **Step 2: Run to verify it fails**
`docker compose exec -T frontend pnpm exec vitest run src/__tests__/hooks/useCalibration.test.tsx` → FAIL (`useCalibration` not exported).

- [ ] **Step 3: Implement** — append to `frontend/src/hooks/useAnalytics.ts` (the `startISO` helper + `apiGet` import already exist):

```ts
export interface CalibrationBucket {
  conviction: number;
  n: number;
  correct: number;
  incorrect: number;
  mixed: number;
  inconclusive: number;
  hit_rate: number | null;
}

export interface CalibrationOverall {
  scored: number;
  hit_rate: number | null;
  correct: number;
  incorrect: number;
  mixed: number;
  inconclusive: number;
  avg_forward_return_pct: number | null;
}

export interface ProviderCalibrationRow {
  provider: string;
  model: string;
  n: number;
  correct: number;
  incorrect: number;
  hit_rate: number | null;
}

export interface Calibration {
  horizon: number;
  scored: number;
  attributable: number;
  thesis: {
    buckets: CalibrationBucket[];
    brier: number | null;
    prob_map: Record<string, number>;
    overall: CalibrationOverall;
    by_direction: Record<string, { n: number; hit_rate: number | null }>;
  };
  provider: ProviderCalibrationRow[];
}

export function useCalibration(days = 90, horizon = 30) {
  return useQuery({
    queryKey: ["analytics/calibration", days, horizon],
    queryFn: () =>
      apiGet<Calibration>(
        `/api/analytics/calibration/?horizon=${horizon}&start=${startISO(days)}`,
      ),
  });
}
```

- [ ] **Step 4: Run test + typecheck**
```bash
docker compose exec -T frontend pnpm exec vitest run src/__tests__/hooks/useCalibration.test.tsx
docker compose exec -T frontend pnpm exec tsc --noEmit
```
Expected: pass; tsc clean.

- [ ] **Step 5: Commit**
```bash
git add frontend/src/hooks/useAnalytics.ts frontend/src/__tests__/hooks/useCalibration.test.tsx
LEFTHOOK=0 git commit -m "feat(frontend): useCalibration hook + types

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `/scorecard` page + route/nav/command/shortcut

**Files:** Create `frontend/src/pages/ScorecardPage.tsx`, `frontend/src/__tests__/ScorecardPage.test.tsx`; Modify `frontend/src/router.tsx`, `frontend/src/components/layout/SideNav.tsx`, `frontend/src/components/layout/AppLayout.tsx`, `frontend/src/hooks/useKeyboardShortcuts.ts`.

- [ ] **Step 1: Create the page** — `frontend/src/pages/ScorecardPage.tsx`. REQUIREMENT: default-export; a horizon selector (7/30/90) via `useState`; thesis section (overall hit-rate/Brier/scored + a bucket table with an inline hit-rate bar); provider section (table); loading→skeleton, empty→EmptyState. TEMPLATE — verify `Skeleton`/`SkeletonRows`/`EmptyState` import style + Tailwind tokens against a sibling page (e.g. `AnalyticsPage.tsx`/`EventsPage.tsx`):

```tsx
import { useState } from "react";
import { useCalibration } from "@/hooks/useAnalytics";
import { SkeletonRows } from "@/components/Skeleton";   // VERIFY export style
import { EmptyState } from "@/components/EmptyState";    // VERIFY export style

const HORIZONS = [7, 30, 90] as const;

function pct(v: number | null): string {
  return v === null ? "—" : `${(v * 100).toFixed(0)}%`;
}

export default function ScorecardPage() {
  const [horizon, setHorizon] = useState<number>(30);
  const { data, isLoading } = useCalibration(90, horizon);

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Calibration scorecard</h1>
        <div className="flex gap-1 text-sm">
          {HORIZONS.map((h) => (
            <button
              key={h}
              onClick={() => setHorizon(h)}
              className={`rounded border border-rule px-2 py-1 ${
                h === horizon ? "text-fg" : "text-ink-400"
              }`}
            >
              {h}d
            </button>
          ))}
        </div>
      </div>

      {isLoading || !data ? (
        <SkeletonRows rows={6} />
      ) : data.thesis.overall.scored === 0 ? (
        <EmptyState
          title="No scored theses yet"
          body="Calibration sharpens as your theses reach their post-mortem horizon."
        />
      ) : (
        <>
          <section>
            <h2 className="mb-2 font-semibold">Thesis calibration</h2>
            <p className="mb-3 text-sm text-ink-400">
              Hit-rate {pct(data.thesis.overall.hit_rate)} · Brier{" "}
              {data.thesis.brier ?? "—"} · {data.thesis.overall.scored} scored ({horizon}d)
            </p>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-ink-400">
                  <th className="text-left">Conviction</th><th>n</th><th>Hit-rate</th><th></th>
                </tr>
              </thead>
              <tbody>
                {data.thesis.buckets.map((b) => (
                  <tr key={b.conviction} className="border-t border-rule">
                    <td>{b.conviction}</td>
                    <td className="text-center">{b.n}</td>
                    <td className="text-center">{pct(b.hit_rate)}</td>
                    <td className="w-1/2">
                      <div
                        className="h-2 rounded bg-copper-500"
                        style={{ width: `${(b.hit_rate ?? 0) * 100}%` }}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section>
            <h2 className="mb-2 font-semibold">Provider calibration</h2>
            <p className="mb-2 text-sm text-ink-400">
              {data.attributable} of {data.scored} scored theses attributable to a provider.
            </p>
            {data.provider.length === 0 ? (
              <EmptyState title="No provider-attributable theses" />
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-ink-400">
                    <th className="text-left">Provider</th><th className="text-left">Model</th>
                    <th>n</th><th>Hit-rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.provider.map((r) => (
                    <tr key={`${r.provider}-${r.model}`} className="border-t border-rule">
                      <td>{r.provider}</td><td>{r.model}</td>
                      <td className="text-center">{r.n}</td>
                      <td className="text-center">{pct(r.hit_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
```
(Verify token classes `border-rule`/`text-ink-400`/`text-fg`/`bg-copper-500` exist — grep a sibling; adapt. `EmptyState` props per its real interface — `action` is a ReactNode if used.)

- [ ] **Step 2: Wire route + nav + command + shortcut**
- `frontend/src/router.tsx`: `import ScorecardPage from "./pages/ScorecardPage";` + route after `analytics` (or near it): `{ path: "scorecard", element: <ScorecardPage />, handle: { crumb: "Scorecard" } },`
- `frontend/src/components/layout/SideNav.tsx`: add to the `SYSTEM` array after `["/analytics", "Analytics", "AN"]`: `["/scorecard", "Scorecard", "SC"],`
- `frontend/src/components/layout/AppLayout.tsx`: add to `useDefaultCommands` after `go-analytics`: `{ id: "go-scorecard", label: "Go to Scorecard", keywords: "calibration brier conviction hit rate trust", run: () => nav("/scorecard") },`
- `frontend/src/hooks/useKeyboardShortcuts.ts`: add to `SHORTCUTS`: `k: { path: "/scorecard", label: "Scorecard" },` (verify `k` free — taken: d/s/t/h/c/o/a/j/e/b).

- [ ] **Step 3: Render test** — create `frontend/src/__tests__/ScorecardPage.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ScorecardPage from "@/pages/ScorecardPage";
import * as hooks from "@/hooks/useAnalytics";

function mock(data: unknown, isLoading = false) {
  vi.spyOn(hooks, "useCalibration").mockReturnValue({ data, isLoading } as never);
}

describe("ScorecardPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows empty state when nothing scored", () => {
    mock({ horizon: 30, scored: 0, attributable: 0, provider: [],
      thesis: { buckets: [], brier: null, prob_map: {},
        overall: { scored: 0, hit_rate: null, correct: 0, incorrect: 0, mixed: 0, inconclusive: 0, avg_forward_return_pct: null },
        by_direction: {} } });
    render(<ScorecardPage />);
    expect(screen.getByText(/No scored theses yet/i)).toBeInTheDocument();
  });

  it("renders buckets + provider rows when populated", () => {
    mock({ horizon: 30, scored: 2, attributable: 1,
      provider: [{ provider: "claude", model: "claude-opus-4-8", n: 1, correct: 1, incorrect: 0, hit_rate: 1 }],
      thesis: { brier: 0.12, prob_map: {},
        overall: { scored: 2, hit_rate: 0.5, correct: 1, incorrect: 1, mixed: 0, inconclusive: 0, avg_forward_return_pct: 3 },
        by_direction: {},
        buckets: [{ conviction: 5, n: 2, correct: 1, incorrect: 1, mixed: 0, inconclusive: 0, hit_rate: 0.5 }] } });
    render(<ScorecardPage />);
    expect(screen.getByText(/Thesis calibration/i)).toBeInTheDocument();
    expect(screen.getByText("claude")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Verify**
```bash
docker compose exec -T frontend pnpm exec vitest run src/__tests__/ScorecardPage.test.tsx
docker compose exec -T frontend pnpm exec tsc --noEmit
docker compose exec -T frontend pnpm run lint
```
Expected: tests pass; tsc clean; no new lint errors (the `setHorizon` is a user-event handler, NOT setState-in-effect — fine).

- [ ] **Step 5: Commit**
```bash
git add frontend/src/pages/ScorecardPage.tsx frontend/src/__tests__/ScorecardPage.test.tsx \
        frontend/src/router.tsx frontend/src/components/layout/SideNav.tsx \
        frontend/src/components/layout/AppLayout.tsx frontend/src/hooks/useKeyboardShortcuts.ts
LEFTHOOK=0 git commit -m "feat(frontend): /scorecard page + nav + command + g k shortcut

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Full check + docs

**Files:** Modify `CLAUDE.md`, `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md`.

- [ ] **Step 1: Run the full gate** — `make check`. Fix any ruff failures on the new files (`docker compose exec -T web ruff check --fix apps/analytics` + `ruff format apps/analytics`); fix any real pytest/vitest failures. `ty` non-zero is advisory — not a failure. Report the breakdown (ruff / pytest count / frontend eslint+tsc / vitest count).

- [ ] **Step 2: CLAUDE.md note** — under "## Non-obvious conventions", add:
```markdown
- **The calibration scorecard is a 6th analytics surface on its own page.** `apps/analytics/services/calibration.py` aggregates `PostMortem ⋈ Thesis` into thesis-conviction calibration (hit-rate per conviction bucket, a Brier score over a documented `conviction→prob` map `0.5+(c−1)/4×0.4`, by-direction) + provider calibration (per-(provider,model) hit-rate of post-mortem'd theses whose source thread used that provider, via `AIRun.message__thread`). `GET /api/analytics/calibration/?horizon=` (7/30/90, default 30 — one PostMortem per thesis). On-demand, no models/migrations. Surfaces on the dedicated `/scorecard` page (`g k`), not the `/analytics` card grid. `mixed`/`inconclusive` verdicts are counted but excluded from hit-rate/Brier.
```

- [ ] **Step 3: Milestone pointer** — in `docs/superpowers/specs/2026-04-16-ai-dashboard-design.md` under "**Future (not yet in flight):**", add:
```markdown
- **AI calibration scorecard**: `apps/analytics/services/calibration.py` + `GET /api/analytics/calibration/` + a dedicated `/scorecard` page — thesis-conviction calibration (buckets/Brier/curve) + provider hit-rate over `PostMortem ⋈ Thesis`. Feature #3 of the events→briefing→scorecard→recall roadmap. Spec: `docs/superpowers/specs/2026-05-28-ai-scorecard-design.md`; plan: `docs/superpowers/plans/2026-05-28-ai-scorecard.md`.
```

- [ ] **Step 4: Commit**
```bash
git add CLAUDE.md docs/superpowers/specs/2026-04-16-ai-dashboard-design.md
LEFTHOOK=0 git commit -m "docs(scorecard): record convention + milestone pointer

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:** calibration service thesis section (buckets/curve/Brier/overall/by_direction) + provider section → Task 1. Endpoint (`/calibration/`, horizon clamp, 90d default) → Task 2. `useCalibration` hook → Task 3. `/scorecard` page + route/nav/`go-scorecard`/`g k` → Task 4. Docs + full check → Task 5. Spec out-of-scope items (time-series, per-model Brier, manual-close source, leaderboard duplication, scheduling) have no tasks — correct.

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to". All code shown. Frontend tasks carry explicit "verify against sibling files" notes (Skeleton/EmptyState exports + Tailwind tokens), gated by tsc/lint — real verification points, not placeholders.

**3. Type/name consistency:** `calibration(*, start, end, horizon)`, `_prob_for_conviction`, `_thesis_section`, `_provider_section`, `_hit_rate`, `PROB_MAP`, `VALID_HORIZONS` consistent across Task 1 + its tests. The response dict keys (`horizon/scored/attributable/thesis{buckets,brier,prob_map,overall,by_direction}/provider`) match between service (T1), endpoint (T2), the TS `Calibration` interface (T3), and the page (T4). `useCalibration(days, horizon)` 2-arg signature consistent (T3 def ↔ T3 test ↔ T4 page). API path `/api/analytics/calibration/?horizon=&start=` consistent (T2 route ↔ T3 hook).

**Known follow-up flagged in-plan:** the frontend `Skeleton`/`EmptyState` export style + Tailwind tokens (`text-fg`/`bg-copper-500`) are verify-against-real-files points in Task 4, gated by tsc/lint.
