# M16 P4 — Analytics Signals Endpoint + Signals Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the P1 signal engine over `GET /api/analytics/signals/?ticker=X` and surface it in the UI as a "Strategy Signals" analytics card plus a lazy per-ticker watchlist expander.

**Prerequisites:** P1 (signals engine + `IVDaily` model) and P2 (`TradingProfile.strategy_tags` backend field + FE type) must be merged into the working branch before starting — current `main` has neither. Verify before Task 1:

```
docker compose exec web python -c "from apps.market.services.signals.engine import compute_signals; from apps.market.models import IVDaily"
grep -n "strategy_tags" /home/dan/ledger/frontend/src/api/profiles.ts
```

Both must succeed (the import exits 0 silently; the grep prints the `strategy_tags: string[]` type line). If either fails, STOP and land P1/P2 first — without P1, Task 1's `monkeypatch.setattr("apps.market.services.signals.engine.compute_signals", ...)` raises `ModuleNotFoundError` instead of the promised `assert 404 == 200` failures; without P2, Task 5's `selected?.strategy_tags` fails `tsc`/`make lint`.

**Architecture:** A thin on-demand DRF `APIView` in `apps.analytics` (no Celery — analytics convention) calls the P1 engine (`compute_signals` / `compute_market_signals`), adds `meta.iv_rank_n` from `IVDaily`, and documents the shape with a drf-spectacular response serializer. The frontend adds a `useTickerSignals` TanStack-Query hook, a hand-rolled-shell analytics card with family grouping + profile-tag highlighting, and a `TickerChanges`-pattern gated expander on the watchlist detail page.

**Tech Stack:** Django 6 + DRF + drf-spectacular, pytest-django (`django_assert_max_num_queries`), React + TanStack Query v5, vitest + @testing-library/react, Storybook + MSW.

**Spec:** docs/superpowers/specs/2026-07-05-strategy-signals-design.md (§8.2, §9, §10)

## Global Constraints

Repo global constraints (from the M16 interface contract — verbatim):

- Everything runs in Docker. One backend test:
  `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (WORKDIR /app/backend).
  One FE test: `docker compose exec frontend pnpm exec vitest run <path> -t "name"`. Lint: `make lint`.
- Never set MOCK_EXTERNAL on the dev stack.
- Migrations gated by `make check-migrations`; beat tasks inventoried in `apps/core/scheduled_tasks.py`
  in the SAME commit (drift gate); worker/beat need `docker compose restart worker beat` after task changes.
- OpenAPI: `make schema` regenerates backend/schema.yml (commit it); `pnpm gen:api` runs on the HOST
  (broken inside the frontend container).
- DRF exposes FK ids as `*_id`. Section terminal state "done"; parent Snapshot "ready".
- Never log provider exceptions raw when the key rides in the URL — use `safe_err`.
- New FE components ship with co-located `*.stories.tsx` (storyless ratchet at ceiling) and a vitest test.
- Conventional commits (`feat(market):`, `feat(observer):`, `feat(frontend):`, `test:`, `docs:`); frequent.
- CI gate runs pytest `-p no:randomly`; coverage floors backend 86 branch, FE 80/74/77/82; ruff C901 ≤15.

P4-specific constraints:

- **Analytics are on-demand, never scheduled** — plain DRF `APIView` in `apps/analytics/views.py`, service/engine imports deferred inside `get()` (house style; every sibling view does this). No new Celery task, no model, no migration in this phase.
- **The engine is law:** `apps.market.services.signals.engine.compute_signals(ticker, families=None, *, benchmark="$SPX") -> dict[str, dict[str, float | int | str | None]]` and `compute_market_signals() -> dict[str, float | None]`. Both never raise (P1's contract). Do NOT re-implement or wrap signal math in analytics.
- **Empty-input responses must be full contract-valid shapes** (`{"ticker": "", "families": {}, "market": {}, "meta": {"iv_rank_n": 0}}`), never `{}` — the SPA reads nested fields directly (CLAUDE.md dashboard landmine class).
- **`AnalyticsCard`'s render-prop shell cannot render an input before data exists** — the signals card hand-rolls its shell exactly like `UnusualOptionsCard` (frontend map gotcha).
- **Expander queries are gated `enabled: open`** so a long watchlist never fans out a request per ticker at load time (`TickerChanges` pattern).
- **data-testid conventions:** `analytics-card-signals` for the card, `ticker-signals-<ticker>` for the expander body (e2e lanes key off these).
- Schemathesis fuzzes every endpoint for 5xx: the view must survive arbitrary `ticker` values. The engine never raises; NUL-byte/garbage ORM input is already mapped to 400 by `apps.core.exceptions.exception_handler` (see the `REST_FRAMEWORK` comment in `config/settings/base.py:163-172`). Don't add ad-hoc try/except.
- Backend files are ruff-formatted: double quotes, line length 100, isort-ordered imports.

---

### Task 1: Backend — `GET /api/analytics/signals/` view + response serializers + URL

**Files:**
- Create: `backend/apps/analytics/serializers.py`
- Modify: `backend/apps/analytics/views.py` (imports at lines 5–11; new view appended after `ContradictionsView`, which ends at line 249)
- Modify: `backend/apps/analytics/urls.py` (import list lines 3–17, `urlpatterns` lines 19–49)
- Test: `backend/apps/analytics/tests/test_signals_endpoint.py`

**Interfaces:**
- Consumes (produced by P1 — importable once P1 is merged; the Prerequisites check at the top of this plan verifies it):
  - `apps.market.services.signals.engine.compute_signals(ticker: str, families: list[str] | None = None, *, benchmark: str = "$SPX") -> dict[str, dict[str, float | int | str | None]]` — `{family: {signal_name: value|None}}`, never raises, Redis-cached.
  - `apps.market.services.signals.engine.compute_market_signals() -> dict[str, float | None]` — currently `{"ad_line_slope_20d": ...}`, never raises.
  - `apps.market.models.IVDaily` — fields `ticker: CharField(max_length=12)`, `date: DateField()`, `atm_iv: FloatField(null=True)` (+ more); unique `(ticker, date)`.
- Produces (later tasks rely on these EXACT names/shapes):
  - Route `GET /api/analytics/signals/?ticker=X` (URL name `analytics-signals`) returning
    `{"ticker": "AAPL", "families": {<family>: {<signal>: number|string|null}}, "market": {"ad_line_slope_20d": number|null}, "meta": {"iv_rank_n": int}}`.
    Empty/missing `ticker` → `{"ticker": "", "families": {}, "market": {}, "meta": {"iv_rank_n": 0}}` (status 200). Ticker is uppercased server-side.
  - `apps.analytics.views.TickerSignalsView` (class), `apps.analytics.serializers.TickerSignalsResponseSerializer` (drf-spectacular component name `TickerSignalsResponse`).

Steps:

- [ ] Write the failing contract test at `backend/apps/analytics/tests/test_signals_endpoint.py`:

```python
"""Contract tests for GET /api/analytics/signals/ — the strategy-signal readout.

Signal math itself is tested in apps/market (P1); these pin the HTTP contract:
response shape, contract-valid empty default, server-side uppercasing, and the
meta.iv_rank_n row count that lets the UI explain a null iv_rank_252.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


def _fake_compute(ticker, families=None, *, benchmark="$SPX"):
    return {
        "momentum": {"macd_hist": 1.2, "adx": 27.5, "ma_alignment": "20>50>200"},
        "mean_reversion": {"zscore_20d": -1.1},
        "vol_options": {"iv_rank_252": None, "hv_20": 24.5},
        "positioning": {"si_days_to_cover": None},
    }


@pytest.mark.django_db
def test_empty_ticker_returns_contract_valid_empty_shape(api):
    r = api.get("/api/analytics/signals/")
    assert r.status_code == 200
    assert r.json() == {"ticker": "", "families": {}, "market": {}, "meta": {"iv_rank_n": 0}}


@pytest.mark.django_db
def test_payload_shape_families_market_meta(api, monkeypatch):
    monkeypatch.setattr("apps.market.services.signals.engine.compute_signals", _fake_compute)
    monkeypatch.setattr(
        "apps.market.services.signals.engine.compute_market_signals",
        lambda: {"ad_line_slope_20d": 0.42},
    )
    r = api.get("/api/analytics/signals/?ticker=AAPL")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "AAPL"
    assert body["families"]["momentum"]["macd_hist"] == 1.2
    assert body["families"]["momentum"]["ma_alignment"] == "20>50>200"
    assert body["families"]["vol_options"]["iv_rank_252"] is None
    assert body["market"] == {"ad_line_slope_20d": 0.42}
    assert body["meta"] == {"iv_rank_n": 0}


@pytest.mark.django_db
def test_ticker_is_uppercased(api, monkeypatch):
    seen: list[str] = []

    def spy(ticker, families=None, *, benchmark="$SPX"):
        seen.append(ticker)
        return {}

    monkeypatch.setattr("apps.market.services.signals.engine.compute_signals", spy)
    monkeypatch.setattr("apps.market.services.signals.engine.compute_market_signals", lambda: {})
    r = api.get("/api/analytics/signals/?ticker=aapl")
    assert r.status_code == 200
    assert r.json()["ticker"] == "AAPL"
    assert seen == ["AAPL"]


@pytest.mark.django_db
def test_meta_carries_iv_rank_row_count(api, monkeypatch):
    from apps.market.models import IVDaily

    monkeypatch.setattr("apps.market.services.signals.engine.compute_signals", _fake_compute)
    monkeypatch.setattr("apps.market.services.signals.engine.compute_market_signals", lambda: {})
    for i in range(3):
        IVDaily.objects.create(
            ticker="AAPL", date=date(2026, 7, 1) - timedelta(days=i), atm_iv=0.31
        )
    r = api.get("/api/analytics/signals/?ticker=AAPL")
    assert r.status_code == 200
    assert r.json()["meta"] == {"iv_rank_n": 3}
```

Why monkeypatching the engine module works: the view (written below) does the house-style deferred import *inside* `get()` — `from apps.market.services.signals.engine import compute_signals` re-reads the module attribute on every request, so `monkeypatch.setattr("apps.market.services.signals.engine.compute_signals", ...)` is seen.

- [ ] Run it — expect all 4 to FAIL on the missing route:

```
docker compose exec web pytest apps/analytics/tests/test_signals_endpoint.py -v
```

Expected: `4 failed`, each with `AssertionError: assert 404 == 200` (no route registered yet).

- [ ] Create `backend/apps/analytics/serializers.py` (new file — the app has only `aieval_serializers.py` today; this is the home for schema-documentation serializers of the plain-dict analytics views):

```python
"""Response serializers for the analytics views' OpenAPI documentation.

The views build plain dicts (house style); these serializers exist so
drf-spectacular emits a real component for the response shape instead of a
blank object. They are never used to serialize at runtime.
"""

from __future__ import annotations

from rest_framework import serializers


class TickerSignalsMetaSerializer(serializers.Serializer):
    iv_rank_n = serializers.IntegerField(
        help_text="IVDaily rows stored for this ticker; iv_rank_252 is null below 60 rows."
    )


class TickerSignalsResponseSerializer(serializers.Serializer):
    """GET /api/analytics/signals/ — per-ticker {family: {signal: value|null}}."""

    ticker = serializers.CharField(allow_blank=True)
    families = serializers.DictField(
        child=serializers.DictField(child=serializers.JSONField(allow_null=True)),
        help_text=(
            "Signal families (momentum, mean_reversion, vol_options, positioning) -> "
            "{signal_name: number|string|null}. A null value means insufficient inputs "
            "— absent, never invented."
        ),
    )
    market = serializers.DictField(
        child=serializers.FloatField(allow_null=True),
        help_text="Market-wide signals (ad_line_slope_20d).",
    )
    meta = TickerSignalsMetaSerializer()
```

- [ ] Modify `backend/apps/analytics/views.py`. First the import block — the file's imports today (lines 5–11) are:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
```

Replace with (drf_spectacular sorts before rest_framework; first-party import after the third-party block):

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.serializers import TickerSignalsResponseSerializer
```

- [ ] Append the view at the end of `backend/apps/analytics/views.py` (after `ContradictionsView`, which currently ends the file at line 249):

```python
class TickerSignalsView(APIView):
    """Strategy-signal readout for one ticker: {family: {signal: value|null}}.

    On-demand like every analytics view — the engine computes (Redis-cached)
    at request time and never raises; a signal with insufficient inputs is
    null, never invented. meta.iv_rank_n carries the IVDaily row count so a
    young IV rank is not mistaken for a full-year rank.
    """

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="ticker",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Ticker symbol, e.g. AAPL. Blank returns an empty payload.",
            )
        ],
        responses=TickerSignalsResponseSerializer,
    )
    def get(self, request: Request) -> Response:
        from apps.market.models import IVDaily
        from apps.market.services.signals.engine import compute_market_signals, compute_signals

        ticker = (request.query_params.get("ticker") or "").upper()
        if not ticker:
            # Contract-valid empty shape — the SPA reads nested fields directly.
            return Response({"ticker": "", "families": {}, "market": {}, "meta": {"iv_rank_n": 0}})
        families = compute_signals(ticker)
        market = compute_market_signals()
        iv_rank_n = IVDaily.objects.filter(ticker=ticker).count()
        return Response(
            {
                "ticker": ticker,
                "families": families,
                "market": market,
                "meta": {"iv_rank_n": iv_rank_n},
            }
        )
```

- [ ] Modify `backend/apps/analytics/urls.py`. In the import list (lines 3–17), add `TickerSignalsView,` between `ObserverTimelineView,` and `TrackRecordView,` (alphabetical: `Tick` < `Track`):

```python
from apps.analytics.views import (
    AICalibrationDrilldownView,
    AICalibrationView,
    CalibrationDriftView,
    CalibrationDrilldownView,
    CalibrationView,
    ContradictionsView,
    CostPerInsightView,
    LeaderboardView,
    ObserverTimelineView,
    TickerSignalsView,
    TrackRecordView,
    TraderCalibrationView,
    TriggerHeatmapView,
    UnusualOptionsView,
)
```

Then in `urlpatterns`, insert one line between the `unusual-options` entry (currently lines 32–36) and the `track-record` entry (line 37):

```python
    path("signals/", TickerSignalsView.as_view(), name="analytics-signals"),
```

- [ ] Run the contract tests — expect PASS:

```
docker compose exec web pytest apps/analytics/tests/test_signals_endpoint.py -v
```

Expected: `4 passed`.

- [ ] Commit:

```
git add backend/apps/analytics/serializers.py backend/apps/analytics/views.py backend/apps/analytics/urls.py backend/apps/analytics/tests/test_signals_endpoint.py
git commit -m "feat(analytics): GET /api/analytics/signals/ ticker signal readout"
```

---

### Task 2: Backend — query-budget gate for the signals endpoint

**Files:**
- Test (create): `backend/apps/analytics/tests/test_signals_query_budget.py`

**Interfaces:**
- Consumes: route `GET /api/analytics/signals/?ticker=X` from Task 1 (response keys `ticker`/`families`/`market`/`meta`); P1 models `apps.market.models.OHLCBar` (fields `ticker`, `timeframe` — choices include `"1d"` —, `open/high/low/close` Decimal(14,4), `volume` BigInt, `ts` DateTimeField; unique `(ticker, timeframe, ts)`) and `apps.market.models.IVDaily` (`ticker`, `date`, `atm_iv`; unique `(ticker, date)`).
- Produces: nothing consumed later — this is the CI N+1 gate (CLAUDE.md: "Add one per new bounded aggregation").

Steps:

- [ ] Write the budget test at `backend/apps/analytics/tests/test_signals_query_budget.py`. It seeds deep history (300 daily bars for the ticker and the `$SPX` benchmark, 70 IVDaily rows) so any per-row/per-signal N+1 in the request path breaches the cap. The ticker `QBUD` is deliberately unique to this test — the engine Redis-caches per `(family, ticker)` (`market:signals:{family}:{ticker}`), and a shared ticker could serve another test's cached values (a cache hit only *lowers* the count, so the max-assertion stays safe either way, but a unique ticker keeps the run hermetic):

```python
"""N+1 regression gate for GET /api/analytics/signals/.

The signals readout must run in a bounded number of queries that does NOT
scale with history depth. We seed 300 daily bars (ticker + $SPX benchmark)
and 70 IVDaily rows — a per-row or per-signal query pattern would breach the
budget immediately. Same harness as test_dashboard_query_budget
(pytest-django's django_assert_max_num_queries).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.market.models import IVDaily, OHLCBar

# The engine does a handful of bulk reads per family for ONE ticker (bars for
# ticker/benchmark/sector ETF, IVDaily window, short-interest, news, breadth)
# plus the view's IVDaily count. That is constant in row count. 40 leaves
# headroom for legitimate per-family reads; an N+1 over 300 bars or 70 IV rows
# breaches it by an order of magnitude. If this fails, fix the query in the
# engine (apps/market/services/signals/) — do NOT raise the budget.
_QUERY_BUDGET = 40


@pytest.mark.django_db
def test_signals_endpoint_is_query_bounded(django_assert_max_num_queries):
    start = datetime(2025, 6, 2, 21, 0, tzinfo=UTC)
    bars = []
    for sym in ("QBUD", "$SPX"):
        for i in range(300):
            bars.append(
                OHLCBar(
                    ticker=sym,
                    timeframe="1d",
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal(100 + (i % 7)),
                    volume=1_000_000,
                    ts=start + timedelta(days=i),
                )
            )
    OHLCBar.objects.bulk_create(bars)
    IVDaily.objects.bulk_create(
        IVDaily(
            ticker="QBUD",
            date=(start + timedelta(days=i)).date(),
            atm_iv=0.25 + (i % 5) / 100,
        )
        for i in range(70)
    )

    client = APIClient()
    with django_assert_max_num_queries(_QUERY_BUDGET):
        r = client.get("/api/analytics/signals/?ticker=QBUD")
    assert r.status_code == 200
    assert set(r.json()) == {"ticker", "families", "market", "meta"}
```

- [ ] Run it — expect PASS:

```
docker compose exec web pytest apps/analytics/tests/test_signals_query_budget.py -v
```

Expected: `1 passed`. If it FAILS with a query count far above 40, the failure output lists the captured queries — a repeated near-identical `SELECT` (once per bar/IV row/signal) is an N+1 inside the P1 engine; fix it there (single windowed query per series). Do not raise `_QUERY_BUDGET`.

- [ ] Run the whole analytics suite to confirm nothing regressed:

```
docker compose exec web pytest apps/analytics/ -q
```

Expected: all passed, 0 failed.

- [ ] Commit:

```
git add backend/apps/analytics/tests/test_signals_query_budget.py
git commit -m "test(analytics): query-budget gate for the signals endpoint"
```

---

### Task 3: OpenAPI schema + generated FE types

**Files:**
- Modify (generated): `backend/schema.yml`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Consumes: Task 1's route + `TickerSignalsResponseSerializer` (component `TickerSignalsResponse`).
- Produces: drift-gated committed schema files. NOTE: `frontend/src/api/schema.d.ts` is an adoption anchor only — no runtime FE code imports it (Task 4 hand-writes its types, the house convention) — but CI drift-gates both files, so this task MUST land before/with the FE tasks.

Steps:

- [ ] Regenerate the backend schema (runs `manage.py spectacular --file schema.yml --validate` inside `web`):

```
make schema
```

Expected: exit 0. Pre-existing `AutoSchema` warnings for the other plain `APIView`s may print; no *new* error. `backend/schema.yml` is modified.

- [ ] Verify the shape landed:

```
grep -n "/api/analytics/signals/" /home/dan/ledger/backend/schema.yml
grep -n "TickerSignalsResponse" /home/dan/ledger/backend/schema.yml | head -5
```

Expected: the path entry, and the `TickerSignalsResponse` + `TickerSignalsMeta` component schemas (with `iv_rank_n`).

- [ ] Regenerate FE types **on the host** (landmine: `pnpm gen:api` fails silently inside the frontend container — `../backend/schema.yml` is not mounted; project memory `gen-api-frontend-container-broken`):

```
cd /home/dan/ledger/frontend && pnpm gen:api
```

Expected output ends with `../backend/schema.yml → src/api/schema.d.ts` (openapi-typescript success line).

- [ ] Verify:

```
grep -n "analytics/signals" /home/dan/ledger/frontend/src/api/schema.d.ts | head -3
```

Expected: at least one hit (the new path key).

- [ ] Commit both generated files together (the CI drift gate compares them against the views):

```
git add backend/schema.yml frontend/src/api/schema.d.ts
git commit -m "chore(api): regenerate OpenAPI schema + FE types for /api/analytics/signals/"
```

---

### Task 4: FE — `useTickerSignals` hook + shared signal formatting lib

**Files:**
- Modify: `frontend/src/hooks/useAnalytics.ts` (append at end of file, after `useTraderCalibration` which ends at line 391)
- Create: `frontend/src/lib/signalFormat.ts`
- Tests (create): `frontend/src/__tests__/hooks/useTickerSignals.test.tsx`, `frontend/src/__tests__/signalFormat.test.ts`

**Interfaces:**
- Consumes: `apiGet<T>(path)` from `@/api/client` (GETs coalesce 204→null); endpoint contract from Task 1:
  `GET /api/analytics/signals/?ticker=X` → `{"ticker": string, "families": {<family>: {<signal>: number|string|null}}, "market": {"ad_line_slope_20d": number|null}, "meta": {"iv_rank_n": number}}`.
- Produces (Tasks 5 & 7 import these EXACT names):
  - `frontend/src/hooks/useAnalytics.ts`:
    - `export type SignalValue = number | string | null;`
    - `export interface TickerSignals { ticker: string; families: Record<string, Record<string, SignalValue>>; market: Record<string, number | null>; meta: { iv_rank_n: number }; }`
    - `export function useTickerSignals(ticker: string, opts?: { enabled?: boolean })` — queryKey `["analytics/signals", ticker]`, `enabled: (opts?.enabled ?? true) && !!ticker` (the contract's `enabled !!ticker` is the default; `opts.enabled` exists so the watchlist expander can gate on `open`).
  - `frontend/src/lib/signalFormat.ts`:
    - `export const FAMILY_ORDER = ["momentum", "mean_reversion", "vol_options", "positioning"] as const;`
    - `export const FAMILY_LABELS: Record<string, string>` (label per family)
    - `export function formatSignalValue(v: number | string | null | undefined): string` — null/undefined → `"—"`, numbers ≥100 abs → 0 decimals, else 2 decimals, strings pass through.

Steps:

- [ ] Write the failing hook test at `frontend/src/__tests__/hooks/useTickerSignals.test.tsx`:

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";

vi.mock("@/api/client", () => ({ apiGet: vi.fn() }));

import { apiGet } from "@/api/client";
import { useTickerSignals } from "@/hooks/useAnalytics";

const mockApiGet = vi.mocked(apiGet);

const PAYLOAD = {
  ticker: "AAPL",
  families: { momentum: { macd_hist: 1.2 } },
  market: { ad_line_slope_20d: null },
  meta: { iv_rank_n: 0 },
};

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useTickerSignals", () => {
  beforeEach(() => vi.clearAllMocks());

  it("does not fetch with an empty ticker", async () => {
    const { result } = renderHook(() => useTickerSignals(""), { wrapper });
    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"));
    expect(mockApiGet).not.toHaveBeenCalled();
  });

  it("does not fetch when opts.enabled is false (expander gating)", async () => {
    const { result } = renderHook(() => useTickerSignals("AAPL", { enabled: false }), {
      wrapper,
    });
    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"));
    expect(mockApiGet).not.toHaveBeenCalled();
  });

  it("fetches /api/analytics/signals/ with the encoded ticker", async () => {
    mockApiGet.mockResolvedValue(PAYLOAD as never);
    const { result } = renderHook(() => useTickerSignals("AAPL"), { wrapper });
    await waitFor(() => expect(result.current.data).toEqual(PAYLOAD));
    expect(mockApiGet).toHaveBeenCalledWith("/api/analytics/signals/?ticker=AAPL");
  });
});
```

- [ ] Write the failing formatter test at `frontend/src/__tests__/signalFormat.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { FAMILY_LABELS, FAMILY_ORDER, formatSignalValue } from "@/lib/signalFormat";

describe("formatSignalValue", () => {
  it("renders null/undefined as an em dash", () => {
    expect(formatSignalValue(null)).toBe("—");
    expect(formatSignalValue(undefined)).toBe("—");
  });

  it("renders small numbers with 2 decimals, large magnitudes with none", () => {
    expect(formatSignalValue(1.234)).toBe("1.23");
    expect(formatSignalValue(-0.5)).toBe("-0.50");
    expect(formatSignalValue(1523.7)).toBe("1524");
  });

  it("passes strings through verbatim (ma_alignment states)", () => {
    expect(formatSignalValue("20>50>200")).toBe("20>50>200");
  });
});

describe("family constants", () => {
  it("orders the four contract families", () => {
    expect([...FAMILY_ORDER]).toEqual([
      "momentum",
      "mean_reversion",
      "vol_options",
      "positioning",
    ]);
  });

  it("labels every family", () => {
    for (const f of FAMILY_ORDER) expect(FAMILY_LABELS[f]).toBeTruthy();
  });
});
```

- [ ] Run both — expect FAIL on missing exports:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/hooks/useTickerSignals.test.tsx src/__tests__/signalFormat.test.ts
```

Expected: the hook file fails with `TypeError: useTickerSignals is not a function` (module loads, export missing) and the formatter file fails with `Failed to resolve import "@/lib/signalFormat"`.

- [ ] Create `frontend/src/lib/signalFormat.ts`:

```ts
/**
 * Shared presentation helpers for strategy-signal readouts — used by the
 * analytics "Strategy Signals" card and the watchlist per-ticker expander so
 * the two surfaces cannot drift on formatting.
 */

/** The four signal families, in display order (matches the backend engine). */
export const FAMILY_ORDER = [
  "momentum",
  "mean_reversion",
  "vol_options",
  "positioning",
] as const;

export const FAMILY_LABELS: Record<string, string> = {
  momentum: "Momentum / trend",
  mean_reversion: "Mean reversion",
  vol_options: "Volatility / options flow",
  positioning: "Positioning / sentiment",
};

/**
 * Format one signal value for display. Null/undefined renders as an em dash —
 * the backend's "absent, never invented" contract; strings (e.g. ma_alignment
 * "20>50>200") pass through verbatim.
 */
export function formatSignalValue(v: number | string | null | undefined): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    return Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(2);
  }
  return String(v);
}
```

- [ ] Append to `frontend/src/hooks/useAnalytics.ts` (end of file, after the `useTraderCalibration` function that currently closes the file at line 391):

```ts
export type SignalValue = number | string | null;

export interface TickerSignals {
  ticker: string;
  families: Record<string, Record<string, SignalValue>>;
  market: Record<string, number | null>;
  meta: { iv_rank_n: number };
}

/**
 * Strategy-signal readout for one ticker ({family: {signal: value|null}}).
 * `opts.enabled` lets lazy expanders gate the fetch (watchlist pattern); the
 * empty-ticker guard always applies.
 */
export function useTickerSignals(ticker: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["analytics/signals", ticker],
    queryFn: () =>
      apiGet<TickerSignals>(
        `/api/analytics/signals/?ticker=${encodeURIComponent(ticker)}`,
      ),
    enabled: (opts?.enabled ?? true) && !!ticker,
  });
}
```

(`useQuery` and `apiGet` are already imported at the top of the file — lines 1–3.)

- [ ] Re-run both test files — expect PASS:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/hooks/useTickerSignals.test.tsx src/__tests__/signalFormat.test.ts
```

Expected: `2 passed` files, `8 passed` tests total.

- [ ] Commit:

```
git add frontend/src/hooks/useAnalytics.ts frontend/src/lib/signalFormat.ts frontend/src/__tests__/hooks/useTickerSignals.test.tsx frontend/src/__tests__/signalFormat.test.ts
git commit -m "feat(frontend): useTickerSignals hook + shared signal formatting"
```

---

### Task 5: FE — StrategySignalsCard component + vitest test

**Files:**
- Create: `frontend/src/components/analytics/StrategySignalsCard.tsx`
- Test (create): `frontend/src/__tests__/analytics/StrategySignalsCard.test.tsx`

**Interfaces:**
- Consumes:
  - `useTickerSignals(ticker: string, opts?: { enabled?: boolean })` and `interface TickerSignals` from `@/hooks/useAnalytics` (Task 4).
  - `FAMILY_ORDER`, `FAMILY_LABELS`, `formatSignalValue` from `@/lib/signalFormat` (Task 4).
  - `useProfiles()` from `@/hooks/useProfiles` — returns `useQuery` of `TradingProfile[]`; `TradingProfile` (in `@/api/profiles`) carries `id: number`, `name: string`, `active: boolean`, and `strategy_tags: string[]` (added by P2 — see Prerequisites; tag values equal family names — `FAMILY_FOR_TAG` is the identity map per the M16 contract). Normalize with `Array.isArray` before ANY array method: `rows.test.tsx`'s shared AnalyticsPage fetch mock resolves `{ok: true, json: () => Promise.resolve({})}` for EVERY endpoint including `/api/profiles/`, so calling `.find` on raw query data throws `TypeError` the moment Task 6 mounts this card there.
- Produces: `export function StrategySignalsCard()` with `data-testid="analytics-card-signals"` on its root `<section>`, and `data-testid="signals-family-<family>"` per family group; a highlighted family group carries the `border-copper-300` class. Task 6 registers it in the grid and writes its stories.

Steps:

- [ ] Write the failing component test at `frontend/src/__tests__/analytics/StrategySignalsCard.test.tsx` (hook-mocking pattern of `UnusualOptionsCard.test.tsx`; profiles mocked too since the card highlights by the selected profile's tags):

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { StrategySignalsCard } from "@/components/analytics/StrategySignalsCard";

const SIGNALS = {
  ticker: "AAPL",
  families: {
    momentum: { macd_hist: 1.23, adx: 27.1, ma_alignment: "20>50>200" },
    vol_options: { iv_rank_252: null, hv_20: 24.5 },
  },
  market: { ad_line_slope_20d: null },
  meta: { iv_rank_n: 12 },
};

vi.mock("@/hooks/useAnalytics", () => ({
  useTickerSignals: (ticker: string) => ({
    data: ticker ? SIGNALS : undefined,
    isLoading: false,
    error: null,
  }),
}));

vi.mock("@/hooks/useProfiles", () => ({
  useProfiles: () => ({
    data: [
      { id: 1, name: "Momo", active: true, strategy_tags: ["momentum"] },
      { id: 2, name: "VolSeller", active: false, strategy_tags: ["vol_options"] },
    ],
  }),
}));

function enterTicker() {
  fireEvent.change(screen.getByPlaceholderText(/ticker/i), { target: { value: "AAPL" } });
}

describe("StrategySignalsCard", () => {
  it("renders a placeholder before a ticker is entered", () => {
    render(<StrategySignalsCard />);
    expect(screen.getByTestId("analytics-card-signals")).toBeInTheDocument();
    expect(screen.getByText(/enter a ticker/i)).toBeInTheDocument();
  });

  it("groups signals by family and renders values", () => {
    render(<StrategySignalsCard />);
    enterTicker();
    expect(screen.getByText("Momentum / trend")).toBeInTheDocument();
    expect(screen.getByText("Volatility / options flow")).toBeInTheDocument();
    expect(screen.getByText("macd_hist")).toBeInTheDocument();
    expect(screen.getByText("1.23")).toBeInTheDocument();
    expect(screen.getByText("20>50>200")).toBeInTheDocument();
  });

  it("renders a null signal as an em dash with the insufficient-history hint", () => {
    render(<StrategySignalsCard />);
    enterTicker();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
    // iv_rank_252 is null and meta.iv_rank_n=12 < 60 -> the hint explains why.
    expect(screen.getByText(/needs 60 sessions/i)).toBeInTheDocument();
    expect(screen.getByText(/12 collected so far/i)).toBeInTheDocument();
  });

  it("highlights the families matching the active profile's tags", () => {
    render(<StrategySignalsCard />);
    enterTicker();
    expect(screen.getByTestId("signals-family-momentum").className).toContain(
      "border-copper-300",
    );
    expect(screen.getByTestId("signals-family-vol_options").className).not.toContain(
      "border-copper-300",
    );
  });

  it("moves the highlight when another profile is selected", () => {
    render(<StrategySignalsCard />);
    enterTicker();
    fireEvent.change(screen.getByLabelText("Profile"), { target: { value: "2" } });
    expect(screen.getByTestId("signals-family-vol_options").className).toContain(
      "border-copper-300",
    );
    expect(screen.getByTestId("signals-family-momentum").className).not.toContain(
      "border-copper-300",
    );
  });
});
```

- [ ] Run it — expect FAIL:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/analytics/StrategySignalsCard.test.tsx
```

Expected: `Failed to resolve import "@/components/analytics/StrategySignalsCard"`.

- [ ] Create `frontend/src/components/analytics/StrategySignalsCard.tsx`. Hand-rolled shell (NOT the `AnalyticsCard` render-prop — it only renders children once `data` is truthy, so the ticker input could never render pre-data; `UnusualOptionsCard` is the sanctioned pattern, including its input styling):

```tsx
import { useState } from "react";
import { useTickerSignals } from "@/hooks/useAnalytics";
import { useProfiles } from "@/hooks/useProfiles";
import { FAMILY_LABELS, FAMILY_ORDER, formatSignalValue } from "@/lib/signalFormat";

/** iv_rank_252/iv_percentile_252 are null below this many IVDaily rows. */
const IV_RANK_MIN_N = 60;

export function StrategySignalsCard() {
  const [ticker, setTicker] = useState("");
  const [profileId, setProfileId] = useState<number | null>(null);
  const { data, isLoading, error } = useTickerSignals(ticker.toUpperCase());
  const { data: profiles } = useProfiles();

  // Normalize before any array method: profiles query data is not guaranteed
  // to be an array (rows.test.tsx's shared fetch mock resolves {} for every
  // endpoint, /api/profiles/ included) — `{}.find` would throw.
  const profileList = Array.isArray(profiles) ? profiles : [];
  const active = profileList.find((p) => p.active) ?? profileList[0];
  const selected =
    profileId != null ? (profileList.find((p) => p.id === profileId) ?? active) : active;
  const tags = new Set(selected?.strategy_tags ?? []);

  const families = data?.families ?? {};
  const familyNames = FAMILY_ORDER.filter((f) => f in families);
  const ivRankMissing =
    data != null &&
    families.vol_options?.iv_rank_252 == null &&
    data.meta.iv_rank_n < IV_RANK_MIN_N;

  return (
    <section data-testid="analytics-card-signals" className="ledger-surface p-5 md:col-span-2">
      <header className="ledger-eyebrow mb-3">Strategy signals</header>
      <div className="flex gap-2 mb-3">
        <input
          className="w-32 px-2 py-1 bg-slate-900 border border-slate-700 rounded text-sm font-mono text-slate-100"
          placeholder="Ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
        />
        {profileList.length > 0 && (
          <select
            aria-label="Profile"
            className="px-2 py-1 bg-slate-900 border border-slate-700 rounded text-sm text-slate-100"
            value={selected?.id ?? ""}
            onChange={(e) => setProfileId(Number(e.target.value))}
          >
            {profileList.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
      </div>
      {!ticker && <p className="text-sm text-slate-400">Enter a ticker to read its signals.</p>}
      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && <p className="text-sm text-rose-700 dark:text-rose-400">{String(error)}</p>}
      {data && familyNames.length === 0 && (
        <p className="text-sm text-slate-500">No signals computed for {data.ticker}.</p>
      )}
      {data && familyNames.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {familyNames.map((fam) => {
            const highlighted = tags.has(fam);
            return (
              <div
                key={fam}
                data-testid={`signals-family-${fam}`}
                className={`rounded border p-3 ${
                  highlighted ? "border-copper-300" : "border-slate-800"
                }`}
              >
                <h3
                  className={`text-xs uppercase tracking-wide mb-2 ${
                    highlighted ? "text-copper-300" : "text-slate-400"
                  }`}
                >
                  {FAMILY_LABELS[fam] ?? fam}
                  {highlighted && <span className="ml-2 normal-case">· {selected?.name}</span>}
                </h3>
                <table className="w-full text-sm font-mono">
                  <tbody>
                    {Object.entries(families[fam]).map(([name, value]) => (
                      <tr key={name} className="border-t border-slate-800 first:border-t-0">
                        <td className="py-0.5 text-slate-400">{name}</td>
                        <td className="py-0.5 text-right text-slate-100">
                          {formatSignalValue(value)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
      )}
      {data && ivRankMissing && (
        <p className="mt-3 text-xs text-slate-500">
          IV rank needs {IV_RANK_MIN_N} sessions of IV history; {data.meta.iv_rank_n} collected
          so far.
        </p>
      )}
      {data && data.market.ad_line_slope_20d != null && (
        <p className="mt-3 text-xs text-slate-500 font-mono">
          Market A/D 20d slope: {formatSignalValue(data.market.ad_line_slope_20d)}
        </p>
      )}
    </section>
  );
}
```

- [ ] Run the test — expect PASS:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/analytics/StrategySignalsCard.test.tsx
```

Expected: `5 passed`.

- [ ] Commit (the story lands in Task 6 in the SAME PR — the story-coverage ratchet (`src/__tests__/storyCoverage.test.ts`, baseline 35) fails the full vitest run for a story-less `components/analytics/*.tsx`, so do not run the full FE suite between these two commits):

```
git add frontend/src/components/analytics/StrategySignalsCard.tsx frontend/src/__tests__/analytics/StrategySignalsCard.test.tsx
git commit -m "feat(frontend): Strategy Signals analytics card"
```

---

### Task 6: FE — card stories + AnalyticsPage grid registration + testid smoke test

**Files:**
- Create: `frontend/src/components/analytics/StrategySignalsCard.stories.tsx`
- Modify: `frontend/src/pages/AnalyticsPage.tsx` (imports lines 1–5, grid children lines 19–25)
- Modify: `frontend/src/__tests__/testids/rows.test.tsx` (AnalyticsPage describe block, after the `analytics-card-unusual-options` test at lines 283–286)

**Interfaces:**
- Consumes: `StrategySignalsCard` from `@/components/analytics/StrategySignalsCard` (Task 5; testid `analytics-card-signals`); endpoint JSON shape from Task 1; `TickerSignals` type from `@/hooks/useAnalytics` (Task 4). Storybook globals: MSW via `parameters.msw.handlers` + a fresh QueryClient per story (`.storybook/preview.tsx`); `expect`/`userEvent` from `"storybook/test"`.
- Produces: the card mounted on `/analytics`; story-coverage ratchet satisfied for the new component. (The e2e ui lane's `test_analytics_page_renders_all_five_cards` asserts the five existing cards are *visible*, not exclusive — verified at `e2e/ui/test_analytics.py:13-21` — so a sixth card is additive and safe. The e2e **visual** lane is NOT additive-safe: `e2e/visual/test_route_snapshots.py:36` byte-diffs `/analytics` against the committed `e2e/visual/__screenshots__/analytics.png`, which this task makes stale. The baseline is regenerated ONCE, in Task 9 — Task 8 also changes the baselined `/watchlists/:id` route (`watchlist_detail.png`), so a single `make e2e-visual-update` after both lands covers them. Until Task 9's regeneration commit, do not expect `make e2e` / `make e2e-visual` to be green.)

Steps:

- [ ] Add the testid smoke test first (failing). In `frontend/src/__tests__/testids/rows.test.tsx`, inside the `describe("AnalyticsPage", ...)` block, after the `renders analytics-card-unusual-options` test (lines 283–286), add:

```tsx
  it("renders analytics-card-signals", async () => {
    wrap(<AnalyticsPage />);
    expect(screen.getByTestId("analytics-card-signals")).toBeInTheDocument();
  });
```

(The block's first test installs a shared `globalThis.fetch` mock that every later test in the block reuses — and it resolves `{ok: true, json: () => Promise.resolve({})}` for EVERY endpoint, including `/api/profiles/`. That non-array profiles payload is exactly why Task 5's card normalizes with `Array.isArray` into `profileList` instead of calling `profiles?.find(...)`: with the guard in place this block needs no URL-keyed special-casing (unlike the SnapshotComposerPage block below, which had to special-case `/api/profiles/`), and all six tests in the block — the five pre-existing card tests included — keep passing once the card mounts.)

- [ ] Run it — expect FAIL:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/testids/rows.test.tsx -t "renders analytics-card-signals"
```

Expected: `1 failed` — `Unable to find an element by: [data-testid="analytics-card-signals"]`.

- [ ] Register the card in `frontend/src/pages/AnalyticsPage.tsx`. Add the import after the `UnusualOptionsCard` import (line 5):

```tsx
import { StrategySignalsCard } from "@/components/analytics/StrategySignalsCard";
```

and add the JSX child after `<UnusualOptionsCard />` (line 24) inside the grid:

```tsx
        <StrategySignalsCard />
```

- [ ] Re-run — expect PASS:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/testids/rows.test.tsx
```

Expected: all tests in the file pass (including the pre-existing ones).

- [ ] Create `frontend/src/components/analytics/StrategySignalsCard.stories.tsx` (MSW-mocked like `ProviderLeaderboardCard.stories.tsx`; match on path only — MSW ignores query params unless specified; the card also fetches `/api/profiles/` for tag highlighting):

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent } from "storybook/test";
import { http, HttpResponse, delay } from "msw";
import type { TickerSignals } from "@/hooks/useAnalytics";
import { StrategySignalsCard } from "./StrategySignalsCard";

const SIGNALS_URL = "/api/analytics/signals/";
const PROFILES_URL = "/api/profiles/";

const profiles = [
  {
    id: 1,
    name: "Momentum desk",
    style: "momentum swing",
    default_includes: [],
    default_provider: "claude",
    default_model: "",
    active: true,
    strategy_tags: ["momentum"],
  },
];

const populated: TickerSignals = {
  ticker: "AAPL",
  families: {
    momentum: {
      macd_hist: 1.23,
      adx: 27.1,
      rs_vs_spx: 4.2,
      ma_alignment: "20>50>200",
      mom_12_1: 31.8,
    },
    mean_reversion: { zscore_20d: -1.1, bollinger_pct_b: 0.18, rsi2: 7.4 },
    vol_options: { iv_rank_252: 62.0, hv_20: 24.5, put_call_vol: 0.84 },
    positioning: { si_days_to_cover: 2.1, news_sentiment_7d: 0.22 },
  },
  market: { ad_line_slope_20d: 0.35 },
  meta: { iv_rank_n: 85 },
};

const insufficient: TickerSignals = {
  ticker: "AAPL",
  families: {
    momentum: { macd_hist: null, adx: null },
    vol_options: { iv_rank_252: null, hv_20: null },
  },
  market: { ad_line_slope_20d: null },
  meta: { iv_rank_n: 12 },
};

async function typeTicker(canvas: { getByPlaceholderText: (m: RegExp) => HTMLElement }) {
  await userEvent.type(canvas.getByPlaceholderText(/ticker/i), "AAPL");
}

const meta = {
  title: "Content/StrategySignalsCard",
  component: StrategySignalsCard,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Per-ticker strategy-signal readout grouped by family, with the families matching " +
          "the selected profile's strategy_tags highlighted. Self-fetches " +
          "`/api/analytics/signals/` and `/api/profiles/` — mocked here with MSW.",
      },
    },
  },
} satisfies Meta<typeof StrategySignalsCard>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Full readout: four families, the profile-tagged momentum group highlighted. */
export const Populated: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(SIGNALS_URL, () => HttpResponse.json(populated)),
        http.get(PROFILES_URL, () => HttpResponse.json(profiles)),
      ],
    },
  },
  play: async ({ canvas }) => {
    await typeTicker(canvas);
    await expect(await canvas.findByText("macd_hist")).toBeVisible();
    await expect(canvas.getByText("20>50>200")).toBeVisible();
    await expect(canvas.getByText("Momentum desk")).toBeVisible();
  },
};

/** Nulls everywhere + a young IV history: em dashes and the min-n hint. */
export const InsufficientHistory: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(SIGNALS_URL, () => HttpResponse.json(insufficient)),
        http.get(PROFILES_URL, () => HttpResponse.json(profiles)),
      ],
    },
  },
  play: async ({ canvas }) => {
    await typeTicker(canvas);
    await expect(await canvas.findByText(/needs 60 sessions/i)).toBeVisible();
    await expect((await canvas.findAllByText("—")).length).toBeGreaterThan(0);
  },
};

/** Request in flight — the handler never resolves, so the "Loading…" line stays. */
export const Loading: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(SIGNALS_URL, async () => {
          await delay("infinite");
          return HttpResponse.json(populated);
        }),
        http.get(PROFILES_URL, () => HttpResponse.json(profiles)),
      ],
    },
  },
  play: async ({ canvas }) => {
    await typeTicker(canvas);
    await expect(await canvas.findByText(/loading/i)).toBeVisible();
  },
};

/** Server error — the failure surface (retries are off in the story QueryClient). */
export const Errored: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(SIGNALS_URL, () =>
          HttpResponse.json({ message: "boom" }, { status: 500 }),
        ),
        http.get(PROFILES_URL, () => HttpResponse.json(profiles)),
      ],
    },
  },
  play: async ({ canvas }) => {
    await typeTicker(canvas);
    await expect(await canvas.findByText(/boom/i)).toBeVisible();
  },
};
```

- [ ] Confirm the story-coverage ratchet is satisfied (the new component now has a co-located story):

```
docker compose exec frontend pnpm exec vitest run src/__tests__/storyCoverage.test.ts
```

Expected: `1 passed`.

- [ ] Commit:

```
git add frontend/src/components/analytics/StrategySignalsCard.stories.tsx frontend/src/pages/AnalyticsPage.tsx frontend/src/__tests__/testids/rows.test.tsx
git commit -m "feat(frontend): register Strategy Signals card on the analytics grid + stories"
```

---

### Task 7: FE — watchlist per-ticker signals expander + vitest test

**Files:**
- Create: `frontend/src/pages/watchlist/TickerSignals.tsx`
- Test (create): `frontend/src/__tests__/TickerSignals.test.tsx`

**Interfaces:**
- Consumes: `useTickerSignals(ticker, { enabled: open })` + `TickerSignals` type from `@/hooks/useAnalytics` (Task 4 — the `opts.enabled` arg exists exactly for this gating); `FAMILY_ORDER`, `FAMILY_LABELS`, `formatSignalValue` from `@/lib/signalFormat` (Task 4). The hook's `queryFn` calls `apiGet` from `@/api/client`, so tests spy/mock at that seam.
- Produces: `export function TickerSignals({ ticker }: { ticker: string })` — collapsed by default, fetches ONLY when expanded, body `data-testid={`ticker-signals-${ticker}`}`. Task 8 mounts it in `WatchlistDetail` and writes its story.

Steps:

- [ ] Write the failing test at `frontend/src/__tests__/TickerSignals.test.tsx` (sibling pattern: `TickerChanges.test.tsx`; no `MemoryRouter` needed — the component renders no `<Link>`):

```tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { ReactNode } from "react";

vi.mock("@/api/client", () => ({ apiGet: vi.fn() }));

import { apiGet } from "@/api/client";
import { TickerSignals } from "@/pages/watchlist/TickerSignals";

const mockApiGet = vi.mocked(apiGet);

const PAYLOAD = {
  ticker: "NVDA",
  families: {
    momentum: { macd_hist: 1.23, ma_alignment: "20>50>200" },
    vol_options: { iv_rank_252: null },
  },
  market: { ad_line_slope_20d: null },
  meta: { iv_rank_n: 12 },
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("TickerSignals", () => {
  beforeEach(() => vi.clearAllMocks());

  it("is collapsed by default and fetches nothing until expanded", () => {
    render(<TickerSignals ticker="NVDA" />, { wrapper });
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("Signals")).toBeInTheDocument();
    expect(mockApiGet).not.toHaveBeenCalled();
  });

  it("expands to a per-family readout with em dashes for nulls", async () => {
    mockApiGet.mockResolvedValue(PAYLOAD as never);
    render(<TickerSignals ticker="NVDA" />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /signals/i }));
    await waitFor(() =>
      expect(screen.getByTestId("ticker-signals-NVDA")).toHaveTextContent("macd_hist 1.23"),
    );
    expect(mockApiGet).toHaveBeenCalledWith("/api/analytics/signals/?ticker=NVDA");
    expect(screen.getByTestId("ticker-signals-NVDA")).toHaveTextContent("iv_rank_252 —");
    expect(screen.getByText(/Momentum \/ trend/)).toBeInTheDocument();
  });

  it("shows a friendly message when no signals computed", async () => {
    mockApiGet.mockResolvedValue({
      ticker: "TSLA",
      families: {},
      market: {},
      meta: { iv_rank_n: 0 },
    } as never);
    render(<TickerSignals ticker="TSLA" />, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: /signals/i }));
    await waitFor(() =>
      expect(screen.getByText(/No signals computed for TSLA yet/)).toBeInTheDocument(),
    );
  });
});
```

- [ ] Run it — expect FAIL:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/TickerSignals.test.tsx
```

Expected: `Failed to resolve import "@/pages/watchlist/TickerSignals"`.

- [ ] Create `frontend/src/pages/watchlist/TickerSignals.tsx` (mirror of `TickerChanges.tsx` — same chrome classes, same lazy contract):

```tsx
import { useState } from "react";
import { useTickerSignals } from "@/hooks/useAnalytics";
import { FAMILY_LABELS, FAMILY_ORDER, formatSignalValue } from "@/lib/signalFormat";

/**
 * Per-ticker strategy-signal readout for the watchlist. Same lazy-expander
 * contract as TickerChanges: nothing fetches until the row is expanded, so a
 * long watchlist doesn't fan out a request per ticker at load time.
 */
export function TickerSignals({ ticker }: { ticker: string }) {
  const [open, setOpen] = useState(false);
  const q = useTickerSignals(ticker, { enabled: open });
  const families = q.data?.families ?? {};
  const familyNames = FAMILY_ORDER.filter((f) => f in families);

  return (
    <div className="border-b border-rule last:border-b-0">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center justify-between py-2 text-sm hover:text-copper-300"
      >
        <span className="font-medium text-ink-100">{ticker}</span>
        <span className="text-ink-400">{open ? "Hide" : "Signals"}</span>
      </button>
      {open && (
        <div className="pb-3 text-sm" data-testid={`ticker-signals-${ticker}`}>
          {q.isLoading ? (
            <span className="text-ink-500">Loading…</span>
          ) : q.isError ? (
            <span className="text-ink-500">
              {(q.error as Error)?.message ?? "Signals unavailable."}
            </span>
          ) : familyNames.length === 0 ? (
            <span className="text-ink-500">No signals computed for {ticker} yet.</span>
          ) : (
            <div className="space-y-1 font-mono text-[12px] text-ink-300">
              {familyNames.map((fam) => (
                <p key={fam}>
                  <span className="text-ink-500">{FAMILY_LABELS[fam] ?? fam}:</span>{" "}
                  {Object.entries(families[fam])
                    .map(([name, value]) => `${name} ${formatSignalValue(value)}`)
                    .join(" · ")}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] Run the test — expect PASS:

```
docker compose exec frontend pnpm exec vitest run src/__tests__/TickerSignals.test.tsx
```

Expected: `3 passed`.

- [ ] Commit:

```
git add frontend/src/pages/watchlist/TickerSignals.tsx frontend/src/__tests__/TickerSignals.test.tsx
git commit -m "feat(frontend): watchlist per-ticker signals expander"
```

---

### Task 8: FE — mount the expander in WatchlistDetail + expander story + regression check

**Files:**
- Modify: `frontend/src/pages/WatchlistDetail.tsx` (import block lines 1–5; JSX after the "What changed since your last look" section, lines 46–57)
- Create: `frontend/src/pages/watchlist/TickerSignals.stories.tsx`
- Test (existing, must stay green): `frontend/src/__tests__/WatchlistDetail.test.tsx`

**Interfaces:**
- Consumes: `TickerSignals` from `./watchlist/TickerSignals` (Task 7 — collapsed by default, zero fetches until expanded, so mounting it per symbol adds NO load-time requests); `wl.symbols: {id: number; ticker: string; sort_order: number}[]` from the existing `useWatchlist` hook. Endpoint JSON shape from Task 1 for the story's MSW handler.
- Produces: a "Strategy signals" section on `/watchlists/:id` rendering one `TickerSignals` row per symbol; a co-located story (the storybook glob is `../src/**/*.stories.*` — pages/ stories are picked up; the story-coverage ratchet only scans `components/` dirs, but the M16 contract requires a story for EVERY new component). This changes the `/watchlists/:id` render, staling the e2e visual baseline `e2e/visual/__screenshots__/watchlist_detail.png` (`test_watchlist_detail_snapshot`, `e2e/visual/test_route_snapshots.py:60-66`) — regenerated together with `analytics.png` in Task 9.

Steps:

- [ ] Modify `frontend/src/pages/WatchlistDetail.tsx`. Add the import after the `TickerChanges` import (line 4):

```tsx
import { TickerSignals } from "./watchlist/TickerSignals";
```

Then add a sibling section AFTER the existing "What changed since your last look" section (which currently spans lines 46–57, ending `)}` before `</main>`):

```tsx
      {wl.symbols.length > 0 && (
        <section>
          <h2 className="mb-1 text-sm font-semibold text-ink-300">
            Strategy signals
          </h2>
          <div className="ledger-surface px-4">
            {wl.symbols.map((s) => (
              <TickerSignals key={s.id} ticker={s.ticker} />
            ))}
          </div>
        </section>
      )}
```

- [ ] Run the existing WatchlistDetail suite — it must stay green (its ticker assertions are scoped to `getByRole("link", ...)` precisely because tickers also appear in expander buttons, so the extra button rows are safe; the new component's query is `enabled: false` while collapsed, so no unmocked fetch fires):

```
docker compose exec frontend pnpm exec vitest run src/__tests__/WatchlistDetail.test.tsx src/__tests__/TickerChanges.test.tsx
```

Expected: all passed, 0 failed. If `getByText`-style multiple-match errors appear, the fix is to scope the EXISTING assertion by role (the file already does this for links) — do not remove the new section.

- [ ] Create `frontend/src/pages/watchlist/TickerSignals.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent } from "storybook/test";
import { http, HttpResponse } from "msw";
import type { TickerSignals as TickerSignalsPayload } from "@/hooks/useAnalytics";
import { TickerSignals } from "./TickerSignals";

const SIGNALS_URL = "/api/analytics/signals/";

const payload: TickerSignalsPayload = {
  ticker: "NVDA",
  families: {
    momentum: { macd_hist: 1.23, adx: 27.1, ma_alignment: "20>50>200" },
    vol_options: { iv_rank_252: null, hv_20: 24.5 },
  },
  market: { ad_line_slope_20d: null },
  meta: { iv_rank_n: 12 },
};

const meta = {
  title: "Content/TickerSignals",
  component: TickerSignals,
  tags: ["ai-generated"],
  args: { ticker: "NVDA" },
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Watchlist lazy expander: a per-ticker strategy-signal readout that fetches " +
          "`/api/analytics/signals/` only once expanded (no load-time request storm).",
      },
    },
  },
} satisfies Meta<typeof TickerSignals>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Collapsed by default — nothing fetched, just the row button. */
export const Collapsed: Story = {
  parameters: {
    msw: { handlers: [http.get(SIGNALS_URL, () => HttpResponse.json(payload))] },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("NVDA")).toBeVisible();
    await expect(canvas.getByText("Signals")).toBeVisible();
  },
};

/** Expanded: compact per-family lines, em dash for null signals. */
export const Expanded: Story = {
  parameters: {
    msw: { handlers: [http.get(SIGNALS_URL, () => HttpResponse.json(payload))] },
  },
  play: async ({ canvas }) => {
    await userEvent.click(canvas.getByRole("button", { name: /signals/i }));
    await expect(await canvas.findByText(/macd_hist 1.23/)).toBeVisible();
    await expect(canvas.getByText(/iv_rank_252 —/)).toBeVisible();
  },
};

/** Expanded with no computed signals — the friendly empty line. */
export const NoSignals: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get(SIGNALS_URL, () =>
          HttpResponse.json({
            ticker: "NVDA",
            families: {},
            market: {},
            meta: { iv_rank_n: 0 },
          }),
        ),
      ],
    },
  },
  play: async ({ canvas }) => {
    await userEvent.click(canvas.getByRole("button", { name: /signals/i }));
    await expect(await canvas.findByText(/No signals computed for NVDA yet/)).toBeVisible();
  },
};
```

- [ ] Run the story-coverage ratchet once more (unchanged expectation — pages/ isn't scanned, but confirm nothing else regressed):

```
docker compose exec frontend pnpm exec vitest run src/__tests__/storyCoverage.test.ts
```

Expected: `1 passed`.

- [ ] Commit:

```
git add frontend/src/pages/WatchlistDetail.tsx frontend/src/pages/watchlist/TickerSignals.stories.tsx
git commit -m "feat(frontend): mount signals expander on WatchlistDetail + story"
```

---

### Task 9: Full verification sweep + e2e visual baseline regeneration

**Files:**
- Modify (regenerated): `e2e/visual/__screenshots__/analytics.png`, `e2e/visual/__screenshots__/watchlist_detail.png` (stale since Tasks 6/8 — the visual lane byte-diffs both routes)
- Otherwise none (fix-forward only if a gate reds).

**Interfaces:**
- Consumes: everything above. The complete P4 surface: `GET /api/analytics/signals/` (view+serializer+URL+2 test files), regenerated `backend/schema.yml` + `frontend/src/api/schema.d.ts`, `useTickerSignals` + `signalFormat`, `StrategySignalsCard` (+story, +grid, +testid test), `TickerSignals` expander (+story, +WatchlistDetail mount), 5 new FE test files.
- Produces: a green P4 slice ready for review/merge, including regenerated + committed e2e visual baselines for the two changed routes (without them, the next `make e2e` reds the visual lane).

Steps:

- [ ] Backend suite for the touched app:

```
docker compose exec web pytest apps/analytics/ -q
```

Expected: all passed (including the two new files), 0 failed.

- [ ] Migration drift gate (P4 adds no models — this must be a no-op):

```
make check-migrations
```

Expected: exit 0, no missing migrations.

- [ ] Full frontend suite (coverage floors 80/74/77/82 + story ratchet + type checks inside vitest run):

```
docker compose exec frontend pnpm test -- --run
```

Expected: 0 failed; coverage thresholds met (the new files all ship with tests).

- [ ] Full lint (ruff + mypy zero-baseline + import-linter + deptry + semgrep rules backend; eslint + depcruise + type-coverage frontend). Note: `apps.market.services.signals.engine` is NOT in the import-linter forbidden list (only fungible vendor modules are) — analytics importing the engine is sanctioned, same as `apps.market.returns`:

```
make lint
```

Expected: exit 0 (`ty` is advisory and may warn; ruff/mypy/eslint/depcruise must be clean).

- [ ] Regenerate the e2e visual baselines. Task 6 changed the `/analytics` render (sixth card) and Task 8 changed `/watchlists/:id` (signals section), and the visual lane byte-diffs both routes against committed screenshots (`e2e/visual/test_route_snapshots.py:36` — `("/analytics", "analytics", "analytics")` — and `test_watchlist_detail_snapshot` at lines 60–66), so without this step the next `make e2e` reds:

```
make e2e-visual-update
git diff --stat e2e/visual/__screenshots__/
```

`make e2e-visual-update` brings the e2e overlay up itself (`compose.e2e.yaml`, `MOCK_EXTERNAL=true`), wipes `__screenshots__/` inside the worker container (baselines are root-owned there), and re-captures every route. Expected `git diff --stat`: exactly two files changed — `analytics.png` and `watchlist_detail.png`. The lane is deterministic, so any OTHER changed baseline means a dirty e2e stack — investigate (`make e2e-down`, retry), do not commit it. Open both PNGs and eyeball them: analytics shows six cards including "Strategy signals"; watchlist detail shows the new "Strategy signals" section with collapsed per-ticker rows.

- [ ] Tear the e2e stack down and commit the regenerated baselines:

```
make e2e-down
git add e2e/visual/__screenshots__/analytics.png e2e/visual/__screenshots__/watchlist_detail.png
git commit -m "test(e2e): regenerate visual baselines for signals card + watchlist expander"
```

- [ ] Confirm no schema drift remains (both generated files committed in Task 3, nothing regenerated since Task 1's view landed before Task 3):

```
git status --short
```

Expected: empty (clean tree). If `backend/schema.yml` shows modified, a later change touched the API surface — rerun Task 3's steps and amend with a `chore(api):` commit.

- [ ] Optional smoke on the live dev stack (`make dev` running): open `http://127.0.0.1:5173/analytics` (shortcut `g a`), type a watchlist ticker into the Strategy Signals card, confirm families render with values or "—"; then open a watchlist detail page and expand a "Signals" row. On a fresh dev DB most values are legitimately "—" (thin history) — that IS the degraded contract, not a bug.
