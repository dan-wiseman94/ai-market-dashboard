# Frontend Test Coverage Expansion — Design

**Status:** draft 2026-04-18
**Scope:** `frontend/src/` vitest test suite
**Predecessor context:** M1–M6 shipped (`m6-observer`); M7 (event triggers) is next.

## Goal

Build a thorough vitest regression net across the untested frontend surface so M7 can land without silently breaking M1–M6, and so every page, component, hook, API module, and the `WebSocketProvider` in `frontend/src/` has deterministic coverage for happy paths, error states, every conditional branch, interactions, and accessibility queries.

## Non-goals

- **Playwright / browser E2E.** `CLAUDE.md` routes E2E to `playwright-python` backend-side. The frontend suite stays jsdom+vitest.
- **CI coverage gate.** v8 coverage reporter lands as report-only visibility (per user decision). No `make check` failure on threshold regressions.
- **New runtime deps.** No MSW, no Playwright, no storybook. Only `@vitest/coverage-v8` dev dep.
- **Component refactors to enable testability.** If a component is untestable without a refactor, it is flagged in the Risk Register for follow-up; the refactor itself is not part of this work.
- **Backend tests.** Out of scope.
- **Rewriting the 14 existing tests.** They stay as-is except where they collide with new helpers (e.g. ad-hoc `vi.stubGlobal("fetch")` migrating to `mockApi(...)` *in files we are already touching for Phase 5 audit*). No gratuitous churn.

## Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Thorough per-unit depth (happy + all error/branch/interaction/a11y paths) | User decision. Regression net needs teeth; smoke-level would miss the subtle breaks M7 refactors are most likely to cause. |
| 2 | All ~55 untested units in one coordinated spec, 5 phased batches | User decision. Keeps helper conventions consistent across the whole surface; each phase stays bite-sized. |
| 3 | Bottom-up phase order: APIs → hooks → components → pages → realtime | Each later batch sits on tested primitives; a broken API mock surfaces in one place instead of 9 page tests. |
| 4 | Extend `testUtils.tsx` with `mockApi` / `mockApiError` / `installFakeWebSocket` (Approach B) | Zero new runtime deps; matches existing `renderWithProviders` + `mockFetch` style; scales across ~250 tests without boilerplate drift. MSW rejected as overkill for jsdom-only testing with no E2E layer. |
| 5 | Layered WebSocket mocking: fake global `WebSocket` for `WebSocketProvider` unit tests; stub `subscribe()` for consumer-component tests | Provider gets actual transport-level coverage; consumer tests stay simple and don't re-test the provider's internals. |
| 6 | `v8` coverage reporter, report-only, HTML output to `frontend/coverage/` (gitignored); new `make test-cov` target; CI unchanged | User decision. Visibility without enforcement; zero risk of breaking CI while the suite grows. |
| 7 | One PR per phase | Each phase is small enough to review, big enough to justify its own landing. Rollback surface is clean. |
| 8 | Each test file constructs its fixtures locally in `beforeEach`, never module-global | Isolation per test; one broken fixture doesn't cascade through the file. |

## Scope summary

| Category | Untested units | Approx test count |
|---|---|---|
| API modules | 9 (`market`, `watchlists`, `schwab`, `profiles`, `costs`, `threads`, `snapshots`, `ai`, `observer`) | ~36 |
| Hooks | 19 (every hook in `src/hooks/` except `queryClient`) | ~76 |
| Components | 13 (see §Phase 3) | ~65 |
| Pages | 9 (see §Phase 4) | ~54 |
| Realtime | 1 (`WebSocketProvider`) + audit of existing realtime consumer tests | ~10 |
| **Total** | **~51 new units + 3 audited** | **~241 new tests** |

Expected full-suite runtime after completion: ≤ 25s on vitest's default worker pool.

## Test infrastructure

Three additions land in Phase 1's opening commit, before any API tests:

### `src/__tests__/testUtils.tsx` expansion

Additions (existing exports unchanged):

```ts
// HTTP mocking — typed, one-call-per-test
type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
type Route = `${Method} ${string}`;                     // e.g. "GET /api/market/quotes/"
type Handler =
  | unknown                                             // static JSON body → 200
  | ((body: unknown, url: string) => unknown)           // dynamic body factory
  | { status: number; body?: unknown; code?: string; message?: string };

export function mockApi(routes: Record<Route, Handler>): FetchMock;
export function mockApiError(route: Route, status: number, code?: string, message?: string): FetchMock;
export function fetchCalls(mock: FetchMock): Array<{ url: string; method: string; body?: unknown }>;

// React-Query hook wrapper — for renderHook
export function hookWrapper(client?: QueryClient): ({ children }: { children: ReactNode }) => JSX.Element;

// WebSocket faking
export function installFakeWebSocket(): FakeWebSocketController;
export type FakeWebSocketController = {
  sockets: FakeSocket[];                      // every constructed WebSocket
  emit(url: string, data: unknown): void;     // push a message to matching socket
  emitOpen(url: string): void;
  emitClose(url: string, code?: number): void;
  sent(url: string): unknown[];               // messages the app sent
  restore(): void;                             // called in setup.ts afterEach
};

// Router multi-route helper
export function renderWithProviders(ui, {
  client?,
  initialEntries?,
  routePath?,
  routes?: Array<{ path: string; element: ReactNode }>,  // for useNavigate tests
}): RenderResult;
```

Contract: `mockApi` matches `fetch(url, {method})` against route keys by `method + path` (query string ignored for matching but captured via `fetchCalls`). Unmatched calls trigger a test failure with `Error: mockApi: no handler for METHOD /url`. All helpers `vi.stubGlobal` under the hood; `vi.unstubAllGlobals()` runs in the global `afterEach`.

### Fake `WebSocket` class

Pure JS class attached to `globalThis.WebSocket`:
- Records constructor URL + `send()` calls.
- Exposes synchronous `emit(event)` for `open`, `message`, `close`, `error`.
- `readyState` transitions correctly with emit methods.
- `installFakeWebSocket()` returns a `FakeWebSocketController` that owns all sockets constructed while active; `restore()` reassigns the real `WebSocket` and clears the registry.
- Only used in `WebSocketProvider` tests; consumer tests use the layered `subscribe()` stub instead.

### `src/__tests__/setup.ts` additions

```ts
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

vi.mock("lightweight-charts", () => ({ /* existing mock */ }));

afterEach(() => {
  vi.unstubAllGlobals();
  // FakeWebSocketController.restore() is called by its own afterEach hook
  // registered at installFakeWebSocket() time.
});
```

### Coverage reporter

Install `@vitest/coverage-v8` as a dev dependency. Extend `vite.config.ts`:

```ts
test: {
  globals: true,
  environment: "jsdom",
  setupFiles: ["./src/__tests__/setup.ts"],
  env: { VITE_API_BASE_URL: "" },
  coverage: {
    provider: "v8",
    reporter: ["text", "html"],
    include: ["src/**/*.{ts,tsx}"],
    exclude: [
      "src/__tests__/**",
      "src/**/*.d.ts",
      "src/main.tsx",
      "src/vite-env.d.ts",
      "src/router.tsx",  // trivial route declarations; no branches worth covering
    ],
  },
},
```

Add `frontend/coverage/` to `.gitignore`. Add `make test-cov` target in root `Makefile` running `docker compose exec frontend npx vitest --run --coverage`. `make test` (and thus `make check`) stays unchanged.

## Per-category conventions

Every new test file follows the shape for its category. Reviewers use these as the template.

### API module tests — `src/__tests__/api/<module>.test.ts`

Per exported function:
1. **Happy path.** `mockApi({ "GET /api/x/": data })`; call fn; assert returned value equals `data`; assert `fetchCalls` captured exactly one call with the expected method, URL, query string, and JSON body (POST/PUT/PATCH).
2. **Error path.** `mockApiError(...)`; assert rejects with `ApiError` carrying correct `status`/`code`/`message`.
3. **One structural edge case.** 204 No Content, array response shape, query-param encoding of special chars, `credentials`/`headers` expectation — whichever applies to that endpoint.
4. **No extra calls.** Guard against double-fetch regressions.

No React, no QueryClient. Pure `fetch`-boundary tests.

### Hook tests — `src/__tests__/hooks/<useX>.test.tsx`

Using `renderHook` with the `hookWrapper()`:
1. **Loading → success.** Initial render returns `{isLoading: true}`; after resolution, `{data}` matches the mock.
2. **Error propagation.** `mockApiError(...)`; hook exposes `{isError: true, error}` of the expected type.
3. **Query key snapshot.** `queryClient.getQueryCache().findAll()[0].queryKey` equals the expected tuple — locks the key so invalidation contracts don't silently drift.
4. **Mutation specifics** (if applicable). Optimistic update + rollback on error + `onSuccess` invalidates the correct key(s) (assert by spying `queryClient.invalidateQueries`).
5. **`useChannel`** specifically: stubs `subscribe()` from `realtime/subscriptions.ts` and asserts subscribe/unsubscribe lifecycle + handler invocation.

### Component tests — `src/__tests__/<Component>.test.tsx`

Per component:
1. **Render with data.** All props populated; assert key visible content via `getByRole` / `getByText` / `getByLabelText`.
2. **Render empty / loading / error.** Each prop-driven state that has distinct UI.
3. **Interactions.** Every `onClick`, `onChange`, `onSubmit`, keyboard-triggered action via `@testing-library/user-event`; assert the callback prop was called with the expected args.
4. **Accessibility.** At least one `getByRole` assertion; form controls have `getByLabelText` associations. `getByTestId` only when role is genuinely absent.
5. **Conditional rendering.** Each branch in JSX: if a prop toggles a section, both branches get a test.

### Page tests — `src/__tests__/<Page>.test.tsx`

Per page:
1. **Initial render with mocked data.** `mockApi({...})` covers every fetch the page issues on mount; page renders its expected primary content.
2. **Loading state.** Delay resolution; assert skeleton/spinner visible.
3. **Error state.** `mockApiError(...)` on the primary data call; assert error banner/fallback renders.
4. **Critical interactions (2–4).** Navigation (via `renderWithProviders({ routes })` + probe `useLocation`, not spying on `useNavigate` — see Risk R3), form submission, modal open/close, primary CTA.
5. **Child-component wiring.** One smoke check that a key child receives the right props — via visible content, not prop-spying.

### Realtime tests — `src/__tests__/realtime/WebSocketProvider.test.tsx`

Using `installFakeWebSocket()`:
1. **Connects on mount** with URL derived from `VITE_WS_BASE_URL` or default.
2. **Subscribe / unsubscribe.** `subscribe("channel", handler)` registers; `unsubscribe` removes cleanly; handler is invoked only for messages on its channel.
3. **Message routing.** `thread.123` messages go to `thread.123` subscribers, not `thread.456`.
4. **Malformed JSON.** Non-JSON `event.data` is logged and does not crash the provider.
5. **Reconnect on close.** After `emitClose`, provider opens a new socket with backoff; `sockets.length` advances.
6. **No reconnect after unmount.** Pending reconnect timer is cleared.

## Phase inventory

### Phase 1 — API modules (9 units → ~36 tests)

Alphabetical:
- `src/api/ai.ts`
- `src/api/costs.ts`
- `src/api/market.ts`
- `src/api/observer.ts`
- `src/api/profiles.ts`
- `src/api/schwab.ts`
- `src/api/snapshots.ts`
- `src/api/threads.ts`
- `src/api/watchlists.ts`

Phase opens with the `testUtils.tsx` expansion + coverage-reporter wiring + `setup.ts` global afterEach. Everything downstream depends on these helpers.

### Phase 2 — Hooks (19 units → ~76 tests)

Alphabetical:
- `useAiModels`, `useAiUsage`, `useChannel`, `useCosts`, `useCreateConsultThread`, `useCreateSnapshot`, `useHealth`, `useMarketContext`, `useOhlc`, `usePositions`, `useProfiles`, `useProviderConfigs`, `useQuotes`, `useSchedules`, `useSchwabStatus`, `useSnapshot`, `useThread`, `useWatchlist`, `useWatchlists`.

(`queryClient.ts` is already tested and is not a hook in the traditional sense.)

### Phase 3 — Components (13 units → ~65 tests)

Alphabetical:
- `BranchTabs`, `CompareDialog`, `CostChip`, `MarketContextStrip`, `PositionsTable`, `ProviderConfigCard`, `ProviderModelPicker`, `QuoteCell`, `SchwabConnectionCard`, `SnapshotSectionPicker`, `StopButton`, `StreamingMessage`, `WatchlistTable`.

### Phase 4 — Pages (9 units → ~54 tests)

Alphabetical:
- `CostsPage`, `Dashboard`, `ProfilesPage`, `Settings`, `SnapshotComposerPage`, `ThreadDetailPage`, `ThreadsPage`, `WatchlistDetail`, `WatchlistsList`.

### Phase 5 — Realtime (1 unit + audit → ~10 tests)

- New: `WebSocketProvider` (`src/__tests__/realtime/WebSocketProvider.test.tsx`).
- Audit: `NotificationBell.test.tsx`, `ObserverTimelinePage.test.tsx` — migrate any ad-hoc raw-event mocking to the `subscribe()` helper for convention alignment. Functional behavior unchanged.
- Post-landing: run `make test-cov` and record the coverage numbers in the phase PR description for reference.

## Risk register

| ID | Risk | Mitigation |
|---|---|---|
| R1 | `lightweight-charts` mock already global; pages embedding `Chart` inherit it | Verified in existing `Chart.test.tsx`; no change needed. Spot-check in Phase 4. |
| R2 | `html2canvas` usage in `ChartCaptureButton` (already mocked inline) | Add shared `mockHtml2Canvas()` helper during Phase 3 if a page embeds it; otherwise keep inline. |
| R3 | Spying on `useNavigate` is flaky with `MemoryRouter` | Use `renderWithProviders({ routes })` + `useLocation` probe component; assert `location.pathname` changes instead of spying on `useNavigate`. |
| R4 | Pages with many concurrent fetches (e.g. `Dashboard`) | `mockApi` matches by method+path; each fetch gets its own route key. Document in helper docstring. |
| R5 | React Query cache hits skipping fetches across renders | Default `newQueryClient()` per test already isolates caches; hook/page tests must not share a QueryClient across `renderHook` calls in one test. |
| R6 | `StreamingMessage` event ordering is non-deterministic | Order-agnostic assertions where the contract allows; assert concatenated final text where order does matter. |
| R7 | `SchwabConnectionCard` OAuth redirect navigates the jsdom window | Stub `window.location.assign` / `window.open`; assert called with expected URL. |
| R8 | `Settings` page is the largest untested surface (providers + credentials + profiles + secrets) | Allow splitting into `Settings.providers.test.tsx` / `Settings.credentials.test.tsx` / etc. if the single file exceeds ~300 lines. Decision left to the executing agent. |
| R9 | Coverage % falling far below expectation signals a missed category | After Phase 5 lands, expect lines coverage ≈ 85–90% for `src/api/`, 80–85% for `src/hooks/`, 75–80% for components/pages. Audit if numbers are well under these. |

## Resolved open questions

- **Q-A. `src/router.tsx` excluded from coverage.** Accepted — it's a trivial route declaration file.
- **Q-B. Phase-5 audit of existing realtime tests.** Rewrites allowed for convention alignment; functional behavior must not change.
- **Q-C. Merge cadence.** One PR per phase, conventional-commit prefix `test(frontend):` (matching project style from `CLAUDE.md`).

## Success criteria

1. Every unit listed in §Phase inventory has a dedicated test file following its category convention.
2. `make test` passes with the new suite; full runtime ≤ 25s.
3. `make test-cov` emits an HTML report at `frontend/coverage/index.html`.
4. No new runtime dependencies added to `frontend/package.json` (only `@vitest/coverage-v8` under `devDependencies`).
5. `@testing-library/jest-dom/vitest`, `renderWithProviders`, `mockApi`, `installFakeWebSocket`, and `subscribe()` stubs are the only mocking primitives used by new tests (modulo existing global mocks like `lightweight-charts`).
6. Coverage numbers fall within the ranges in R9 or the deviation is explained in the phase-5 PR.

## Workflow

After this spec is approved and committed, the `writing-plans` skill produces the step-by-step implementation plan (one section per phase, each with subagent-ready task breakdowns). Implementation then follows `subagent-driven-development` or `executing-plans` in the user's preference.
