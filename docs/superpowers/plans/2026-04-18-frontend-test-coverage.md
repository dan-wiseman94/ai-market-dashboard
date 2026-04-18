# Frontend Test Coverage Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land thorough vitest coverage across the ~51 currently-untested units in `frontend/src/` (9 API modules, 19 hooks, 13 components, 9 pages, 1 WebSocketProvider), wire v8 coverage reporter as report-only, and keep the full suite ≤ 25s.

**Architecture:** Extend `src/__tests__/testUtils.tsx` with typed `mockApi` / `installFakeWebSocket` helpers so every test uses one consistent mock idiom. Bottom-up phase order (APIs → hooks → components → pages → realtime) so each batch sits on tested primitives. One PR per phase.

**Tech Stack:** vitest 2.x, @testing-library/react 16, @testing-library/user-event 14, @testing-library/jest-dom, jsdom, @vitest/coverage-v8 (new dev dep).

**Spec:** `docs/superpowers/specs/2026-04-18-frontend-test-coverage-design.md`.

---

## Global conventions (read before starting any task)

**Docker context.** Everything runs inside the `frontend` container. Every test/lint command is prefixed with `docker compose exec frontend ...`. If you see `npx vitest` in a step, run `docker compose exec frontend npx vitest ...`.

**Testing-library queries priority** (required for Phase 3–5): `getByRole` > `getByLabelText` > `getByText` > `getByTestId`. Only fall back when the preceding options are genuinely unavailable.

**Fixture locality.** Each test file constructs its `mockApi(...)` / `installFakeWebSocket()` inside `beforeEach`. Never promote fixtures to module scope inside a test file.

**Coverage sweep.** After writing each unit's test file, run `docker compose exec frontend npx vitest run --coverage src/__tests__/<path>` and open `frontend/coverage/index.html`. Any uncovered non-trivial branch in the target source file → add a test. "Trivial" = `className=` ternaries that only affect styling, or exhaustive `default:` arms on discriminated unions that TypeScript already covers.

**Commits.** One commit per unit task. Commit message prefix is `test(frontend):` matching the project's conventional-commit style.

**Expected coverage ranges after Phase 5** (from the spec's R9): `src/api/` 85-90%, `src/hooks/` 80-85%, components/pages 75-80%. Numbers well under these signal a missed category.

---

## Task 1: Test infrastructure — helpers, coverage, setup

Establishes every helper the rest of the plan uses. Must land before any other phase-1 task.

**Files:**
- Modify: `frontend/src/__tests__/testUtils.tsx`
- Modify: `frontend/src/__tests__/setup.ts`
- Modify: `frontend/vite.config.ts`
- Modify: `frontend/package.json`
- Modify: `.gitignore`
- Modify: `Makefile` (project root)

- [ ] **Step 1: Install coverage reporter**

Run: `docker compose exec frontend npm install -D @vitest/coverage-v8@^2.1.2`
Expected: `frontend/package.json` and `frontend/package-lock.json` (if present) updated with the new devDependency.

- [ ] **Step 2: Rewrite `frontend/src/__tests__/testUtils.tsx`**

Replace the file with:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";

export function newQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

type ProviderOptions = {
  client?: QueryClient;
  initialEntries?: string[];
  routePath?: string;
  routes?: Array<{ path: string; element: ReactNode }>;
};

export function renderWithProviders(ui: ReactElement, opts: ProviderOptions = {}): RenderResult {
  const { client = newQueryClient(), initialEntries, routePath, routes } = opts;
  function Wrapper({ children }: { children: ReactNode }) {
    let router: ReactNode;
    if (routes) {
      router = (
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            {routes.map((r) => (
              <Route key={r.path} path={r.path} element={r.element} />
            ))}
          </Routes>
        </MemoryRouter>
      );
    } else if (routePath) {
      router = (
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path={routePath} element={children} />
          </Routes>
        </MemoryRouter>
      );
    } else {
      router = <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>;
    }
    return <QueryClientProvider client={client}>{router}</QueryClientProvider>;
  }
  return render(ui, { wrapper: Wrapper });
}

/** React-Query-only wrapper for renderHook. */
export function hookWrapper(client: QueryClient = newQueryClient()) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

/** Probe component for asserting router location changed in nav tests. */
export function LocationProbe({ onChange }: { onChange: (path: string) => void }) {
  const loc = useLocation();
  onChange(loc.pathname + loc.search);
  return null;
}

// ---- Fetch mocking -----------------------------------------------------

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type Route = `${Method} ${string}`;
type ErrorHandler = { status: number; body?: unknown; code?: string; message?: string };
type FnHandler = (body: unknown, url: string) => unknown;
type Handler = unknown | FnHandler | ErrorHandler;

export type FetchCall = { url: string; method: string; body?: unknown };

export type FetchMock = {
  calls: FetchCall[];
  restore: () => void;
};

function isErrorHandler(h: Handler): h is ErrorHandler {
  return !!h && typeof h === "object" && "status" in (h as object);
}

export function mockApi(routes: Record<string, Handler>): FetchMock {
  const calls: FetchCall[] = [];
  const entries: Array<[string, string, Handler]> = Object.entries(routes).map(([key, h]) => {
    const [method, path] = key.split(" ", 2);
    return [method, path, h];
  });

  const fetchImpl = vi.fn(async (url: string, opts?: RequestInit) => {
    const method = (opts?.method ?? "GET").toUpperCase();
    const parsed = url.includes("?") ? url.split("?")[0] : url;
    let body: unknown;
    if (opts?.body !== undefined && typeof opts.body === "string") {
      try { body = JSON.parse(opts.body); } catch { body = opts.body; }
    }
    calls.push({ url, method, body });

    const match = entries.find(([m, p]) => m === method && parsed.endsWith(p));
    if (!match) {
      throw new Error(`mockApi: no handler for ${method} ${url}`);
    }
    const [, , handler] = match;
    const resolved = typeof handler === "function" ? (handler as FnHandler)(body, url) : handler;

    if (isErrorHandler(resolved)) {
      return {
        ok: false,
        status: resolved.status,
        statusText: String(resolved.status),
        json: async () => ({ code: resolved.code ?? "error", message: resolved.message ?? "err", ...(resolved.body as object ?? {}) }),
      };
    }
    if (resolved === undefined) {
      return { ok: true, status: 204, json: async () => ({}) };
    }
    return { ok: true, status: 200, json: async () => resolved };
  });
  vi.stubGlobal("fetch", fetchImpl);
  return {
    calls,
    restore: () => { vi.unstubAllGlobals(); },
  };
}

export function mockApiError(route: string, status: number, code = "error", message = "err"): FetchMock {
  return mockApi({ [route]: { status, code, message } });
}

// ---- WebSocket faking --------------------------------------------------

type FakeListener = (ev: MessageEvent | Event | CloseEvent) => void;

export class FakeSocket {
  readyState = 0; // CONNECTING
  listeners: Record<string, FakeListener[]> = {};
  sent: unknown[] = [];
  constructor(public url: string) {}
  addEventListener(type: string, listener: FakeListener): void {
    (this.listeners[type] ??= []).push(listener);
  }
  removeEventListener(type: string, listener: FakeListener): void {
    this.listeners[type] = (this.listeners[type] ?? []).filter((l) => l !== listener);
  }
  send(data: string): void {
    try { this.sent.push(JSON.parse(data)); } catch { this.sent.push(data); }
  }
  close(): void {
    this.readyState = 3; // CLOSED
    (this.listeners.close ?? []).forEach((l) => l(new Event("close") as CloseEvent));
  }
  emitOpen(): void {
    this.readyState = 1;
    (this.listeners.open ?? []).forEach((l) => l(new Event("open")));
  }
  emitMessage(data: unknown): void {
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    (this.listeners.message ?? []).forEach((l) => l(new MessageEvent("message", { data: payload })));
  }
  emitClose(code = 1000): void {
    this.readyState = 3;
    (this.listeners.close ?? []).forEach((l) =>
      l(new CloseEvent("close", { code })),
    );
  }
}

export type FakeWebSocketController = {
  sockets: FakeSocket[];
  find(urlSuffix: string): FakeSocket | undefined;
  restore(): void;
};

export function installFakeWebSocket(): FakeWebSocketController {
  const sockets: FakeSocket[] = [];
  class Stub extends FakeSocket {
    constructor(url: string) {
      super(url);
      sockets.push(this);
    }
  }
  const real = globalThis.WebSocket;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).WebSocket = Stub;
  return {
    sockets,
    find: (suffix) => sockets.find((s) => s.url.endsWith(suffix)),
    restore: () => { (globalThis as typeof globalThis).WebSocket = real; },
  };
}
```

- [ ] **Step 3: Update `frontend/src/__tests__/setup.ts`**

Replace with:

```ts
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});
```

- [ ] **Step 4: Update `frontend/vite.config.ts`**

Replace the `test` block with:

```ts
test: {
  globals: true,
  environment: "jsdom",
  setupFiles: ["./src/__tests__/setup.ts"],
  env: {
    VITE_API_BASE_URL: "",
  },
  coverage: {
    provider: "v8",
    reporter: ["text", "html"],
    include: ["src/**/*.{ts,tsx}"],
    exclude: [
      "src/__tests__/**",
      "src/**/*.d.ts",
      "src/main.tsx",
      "src/vite-env.d.ts",
      "src/router.tsx",
    ],
  },
},
```

- [ ] **Step 5: Add `frontend/coverage/` to `.gitignore`**

Append to `.gitignore`:

```
frontend/coverage/
```

- [ ] **Step 6: Add `test-cov` Makefile target**

Open `Makefile` at repo root. Find the existing `test:` target. Add after it:

```make
test-cov:
	docker compose exec frontend npx vitest run --coverage
```

- [ ] **Step 7: Verify the existing suite still passes**

Run: `docker compose exec frontend npx vitest run`
Expected: All existing tests pass (no regression). `api.test.ts` still uses `vi.stubGlobal("fetch", ...)` inline — that's fine, old pattern still works.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/__tests__/testUtils.tsx frontend/src/__tests__/setup.ts \
        frontend/vite.config.ts frontend/package.json frontend/package-lock.json \
        .gitignore Makefile
git commit -m "test(frontend): expand testUtils with mockApi + fake WebSocket + v8 coverage"
```

---

## Phase 1 — API module tests (9 units)

**Phase convention (reference for every Phase-1 task):**
One test file per API module. Per exported function: happy path, error path, one structural edge case, no-extra-calls assertion. Pure `fetch`-boundary — no React, no QueryClient.

File location: `frontend/src/__tests__/api/<module>.test.ts`.

---

## Task 2: Test `src/api/ai.ts` (Phase 1 opener — full worked example)

**Files:**
- Create: `frontend/src/__tests__/api/ai.test.ts`
- Reference source: `frontend/src/api/ai.ts`

**Exports to cover:** `fetchAiModels`, `fetchProviderConfigs`, `upsertProviderConfig`, `fetchAiUsage`. Note `upsertProviderConfig` has a fallback: PATCH first, and if that 404s, POST — both branches need tests.

- [ ] **Step 1: Write the test file**

```ts
import { afterEach, describe, expect, it } from "vitest";
import {
  fetchAiModels,
  fetchProviderConfigs,
  fetchAiUsage,
  upsertProviderConfig,
} from "@/api/ai";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

afterEach(() => { /* setup.ts afterEach handles unstubAllGlobals */ });

describe("api/ai", () => {
  describe("fetchAiModels", () => {
    it("GETs models with no provider filter by default", async () => {
      const api = mockApi({ "GET /api/schwab/models/": { models: [{ id: "x", name: "X", provider: "claude", input_per_mtok: 1, output_per_mtok: 2, cached_per_mtok: 0, context_window: 100, supports_vision: false }] } });
      const res = await fetchAiModels();
      expect(res.models).toHaveLength(1);
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("GET");
      expect(api.calls[0].url).toMatch(/\/api\/schwab\/models\/$/);
    });

    it("encodes provider query param when passed", async () => {
      const api = mockApi({ "GET /api/schwab/models/": { models: [] } });
      await fetchAiModels("open ai");
      expect(api.calls[0].url).toMatch(/provider=open%20ai/);
    });

    it("propagates ApiError on non-2xx", async () => {
      mockApiError("GET /api/schwab/models/", 500, "server_error", "boom");
      await expect(fetchAiModels()).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe("fetchProviderConfigs", () => {
    it("returns array of ProviderConfig on 200", async () => {
      mockApi({ "GET /api/schwab/providers/": [{ provider: "claude", base_url: "", default_model: "x", enabled: true, supports_vision: true, daily_cost_cap_usd: "5", api_key_present: true }] });
      const res = await fetchProviderConfigs();
      expect(res).toEqual([expect.objectContaining({ provider: "claude" })]);
    });

    it("throws ApiError on 503", async () => {
      mockApiError("GET /api/schwab/providers/", 503);
      await expect(fetchProviderConfigs()).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe("upsertProviderConfig", () => {
    it("PATCHes when the provider exists", async () => {
      const api = mockApi({
        "PATCH /api/schwab/providers/claude/": { provider: "claude", base_url: "", default_model: "y", enabled: true, supports_vision: false, daily_cost_cap_usd: "5", api_key_present: false },
      });
      await upsertProviderConfig("claude", { enabled: true });
      expect(api.calls).toHaveLength(1);
      expect(api.calls[0].method).toBe("PATCH");
      expect(api.calls[0].body).toEqual({ enabled: true });
    });

    it("falls back to POST when PATCH returns 404", async () => {
      const api = mockApi({
        "PATCH /api/schwab/providers/local/": { status: 404, code: "not_found", message: "missing" },
        "POST /api/schwab/providers/": { provider: "local", base_url: "http://x", default_model: "m", enabled: true, supports_vision: false, daily_cost_cap_usd: "1", api_key_present: false },
      });
      await upsertProviderConfig("local", { base_url: "http://x" });
      expect(api.calls.map((c) => c.method)).toEqual(["PATCH", "POST"]);
      expect(api.calls[1].body).toEqual({ provider: "local", base_url: "http://x" });
    });

    it("re-throws non-404 ApiError from PATCH without falling back", async () => {
      mockApiError("PATCH /api/schwab/providers/claude/", 500, "server_error", "boom");
      await expect(upsertProviderConfig("claude", {})).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe("fetchAiUsage", () => {
    it("returns the shaped usage object", async () => {
      mockApi({ "GET /api/schwab/usage/": { today: { claude: "0.0012" } } });
      const res = await fetchAiUsage();
      expect(res.today.claude).toBe("0.0012");
    });
  });
});
```

- [ ] **Step 2: Run and verify pass**

Run: `docker compose exec frontend npx vitest run src/__tests__/api/ai.test.ts`
Expected: 8 tests passing.

- [ ] **Step 3: Coverage sweep**

Run: `docker compose exec frontend npx vitest run --coverage src/__tests__/api/ai.test.ts`
Open `frontend/coverage/src/api/ai.ts.html`. Expect ≥ 95% lines. If the POST fallback line isn't green, add a missing test.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/api/ai.test.ts
git commit -m "test(frontend): cover api/ai happy/error/fallback paths"
```

---

## Task 3: Test `src/api/costs.ts`

**Files:**
- Create: `frontend/src/__tests__/api/costs.test.ts`
- Reference source: `frontend/src/api/costs.ts`

- [ ] **Step 1: Read `src/api/costs.ts` and enumerate its exports**

Note each exported function: name, HTTP method, URL path, request body shape (if any), and response shape. Record the list as comments at the top of the new test file so the test coverage is obvious.

- [ ] **Step 2: Write `frontend/src/__tests__/api/costs.test.ts`**

Apply this Phase 1 template to each exported function (4 tests per function):

```ts
import { describe, expect, it } from "vitest";
import * as costs from "@/api/costs";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

// For each exported function:
// - happy path: mockApi({ "METHOD /path/": responseShape }); assert returned value; assert 1 call; assert body if POST/PATCH.
// - error path: mockApiError("METHOD /path/", 500); assert rejects with ApiError.
// - edge case: for endpoints accepting params → assert query encoding; for DELETE → 204 resolves void; for bodies → JSON-stringify serialization.
// - no-extra-calls: expect(api.calls).toHaveLength(1) after each happy-path call.

describe("api/costs", () => {
  // ... one describe block per exported function
});
```

- [ ] **Step 3: Run tests and verify pass**

Run: `docker compose exec frontend npx vitest run src/__tests__/api/costs.test.ts`
Expected: PASS.

- [ ] **Step 4: Coverage sweep**

Run: `docker compose exec frontend npx vitest run --coverage src/__tests__/api/costs.test.ts`
Open `frontend/coverage/src/api/costs.ts.html`. Any red branch → add a test.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/__tests__/api/costs.test.ts
git commit -m "test(frontend): cover api/costs"
```

---

## Task 4: Test `src/api/market.ts`

**Files:**
- Create: `frontend/src/__tests__/api/market.test.ts`
- Reference source: `frontend/src/api/market.ts`

- [ ] **Step 1: Enumerate market API exports**

Expected: likely `fetchQuotes(tickers)`, `fetchOhlc(ticker, range)`, `fetchPositions()`, `fetchMarketContext()`, chain/news/breadth endpoints. Record each with its URL in a comment block at the top of the test file.

- [ ] **Step 2: Write test file applying the Phase 1 template**

4 tests per function: happy, error (ApiError on non-2xx), edge (query encoding for ticker list, special chars, `t=` repeats, or empty-result shape), no-extra-calls assertion.

Example skeleton:

```ts
import { describe, expect, it } from "vitest";
import { fetchQuotes /* + others */ } from "@/api/market";
import { ApiError } from "@/api/client";
import { mockApi, mockApiError } from "../testUtils";

describe("api/market", () => {
  describe("fetchQuotes", () => {
    it("GETs quotes with ticker params encoded", async () => {
      const api = mockApi({ "GET /api/market/quotes/": { quotes: [{ symbol: "AAPL", last: 100 }] } });
      await fetchQuotes(["AAPL", "MSFT"]);
      expect(api.calls[0].url).toMatch(/AAPL/);
      expect(api.calls[0].url).toMatch(/MSFT/);
    });
    it("propagates ApiError on 502", async () => {
      mockApiError("GET /api/market/quotes/", 502);
      await expect(fetchQuotes(["AAPL"])).rejects.toBeInstanceOf(ApiError);
    });
  });
  // Repeat for each exported fn.
});
```

- [ ] **Step 3: Run + coverage + commit**

Run tests, sweep coverage (`frontend/coverage/src/api/market.ts.html` ≥ 90%), commit:

```bash
git add frontend/src/__tests__/api/market.test.ts
git commit -m "test(frontend): cover api/market"
```

---

## Task 5: Test `src/api/observer.ts`

**Files:** Create `frontend/src/__tests__/api/observer.test.ts`; reference `frontend/src/api/observer.ts`.

- [ ] **Step 1: Enumerate exports.** Likely schedule CRUD (`listSchedules`, `createSchedule`, `updateSchedule`, `deleteSchedule`, `runSchedule`), notifications (`listNotifications`, `markRead`).
- [ ] **Step 2: Apply Phase 1 template.** 4 tests per function: happy, error, edge (e.g., PATCH body serialization, DELETE returning 204, query-string for pagination if present), no-extra-calls.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/api/observer.test.ts
git commit -m "test(frontend): cover api/observer"
```

---

## Task 6: Test `src/api/profiles.ts`

**Files:** Create `frontend/src/__tests__/api/profiles.test.ts`; reference `frontend/src/api/profiles.ts`.

- [ ] **Step 1: Enumerate exports** (list, create, update, delete profile; maybe default selection).
- [ ] **Step 2: Apply Phase 1 template** — happy + error + edge + no-extra-calls per function.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/api/profiles.test.ts
git commit -m "test(frontend): cover api/profiles"
```

---

## Task 7: Test `src/api/schwab.ts`

**Files:** Create `frontend/src/__tests__/api/schwab.test.ts`; reference `frontend/src/api/schwab.ts`.

- [ ] **Step 1: Enumerate exports.** Likely `fetchSchwabStatus`, OAuth start-URL fetch, disconnect, refresh. OAuth start may return a URL for browser redirect — test it returns the URL without triggering navigation.
- [ ] **Step 2: Apply Phase 1 template** for each.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/api/schwab.test.ts
git commit -m "test(frontend): cover api/schwab"
```

---

## Task 8: Test `src/api/snapshots.ts`

**Files:** Create `frontend/src/__tests__/api/snapshots.test.ts`; reference `frontend/src/api/snapshots.ts`.

- [ ] **Step 1: Enumerate exports.** Create snapshot (POST with section list), fetch snapshot by id, image-serve URL helper if any.
- [ ] **Step 2: Apply Phase 1 template.** Edge case: verify POST body structure (sections array, objective text, tickers list).
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/api/snapshots.test.ts
git commit -m "test(frontend): cover api/snapshots"
```

---

## Task 9: Test `src/api/threads.ts`

**Files:** Create `frontend/src/__tests__/api/threads.test.ts`; reference `frontend/src/api/threads.ts`.

- [ ] **Step 1: Enumerate exports.** Create thread, fetch thread, send message, compare-endpoint (fan-out), stop-message. The compare endpoint is the highest-branch — test its body structure carefully (array of provider/model pairs).
- [ ] **Step 2: Apply Phase 1 template.** Edge: compare body shape; stop returns 204.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/api/threads.test.ts
git commit -m "test(frontend): cover api/threads"
```

---

## Task 10: Test `src/api/watchlists.ts`

**Files:** Create `frontend/src/__tests__/api/watchlists.test.ts`; reference `frontend/src/api/watchlists.ts`.

- [ ] **Step 1: Enumerate exports.** List, get by id, create, update tickers, delete.
- [ ] **Step 2: Apply Phase 1 template.**
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/api/watchlists.test.ts
git commit -m "test(frontend): cover api/watchlists"
```

---

## Phase 1 close — run the whole API suite

- [ ] **Step 1: Confirm Phase 1 is green**

Run: `docker compose exec frontend npx vitest run src/__tests__/api/`
Expected: All API tests pass in ≤ 3s.

- [ ] **Step 2: Coverage audit for `src/api/`**

Run: `docker compose exec frontend npx vitest run --coverage src/__tests__/api/`
Open `frontend/coverage/index.html` → `src/api/`. Expect ≥ 85% lines across the folder. Below that, revisit the lowest file before moving to Phase 2.

- [ ] **Step 3: Open Phase 1 PR**

```bash
git push -u origin <branch>
gh pr create --title "test(frontend): phase 1 — API module coverage" --body "$(cat <<'EOF'
## Summary
- Adds `mockApi` / `mockApiError` / `installFakeWebSocket` helpers to `testUtils.tsx`
- Wires `@vitest/coverage-v8` as report-only (new `make test-cov` target)
- Covers all 9 API modules (36+ tests): happy path, ApiError propagation, structural edge cases

## Test plan
- [ ] `make test` passes
- [ ] `make test-cov` produces an HTML report at `frontend/coverage/`
- [ ] Phase 1 coverage ≥ 85% for `src/api/`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Phase 2 — Hook tests (19 units)

**Phase convention:**
One test file per hook at `frontend/src/__tests__/hooks/<useX>.test.tsx`. Using `renderHook` from `@testing-library/react` with `hookWrapper()`. Four standard tests: loading → success, error propagation, query-key snapshot, mutation specifics (only if the hook is a mutation).

---

## Task 11: Test `useAiModels` (Phase 2 opener — full worked example)

**Files:**
- Create: `frontend/src/__tests__/hooks/useAiModels.test.tsx`
- Reference source: `frontend/src/hooks/useAiModels.ts`

Source is trivial — wraps `fetchAiModels` with `useQuery` and key `["ai-models", provider ?? "all"]`.

- [ ] **Step 1: Write the test file**

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAiModels } from "@/hooks/useAiModels";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

describe("useAiModels", () => {
  it("returns models on success and starts in loading state", async () => {
    mockApi({ "GET /api/schwab/models/": { models: [{ id: "x", name: "X", provider: "claude", input_per_mtok: 1, output_per_mtok: 1, cached_per_mtok: 0, context_window: 100, supports_vision: false }] } });
    const { result } = renderHook(() => useAiModels(), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.models).toHaveLength(1);
  });

  it("propagates fetch errors as isError", async () => {
    mockApiError("GET /api/schwab/models/", 500);
    const { result } = renderHook(() => useAiModels(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("uses stable query key including provider filter", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/schwab/models/": { models: [] } });
    renderHook(() => useAiModels("claude"), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["ai-models", "claude"]);
    });
  });

  it("uses 'all' as the default filter value in the query key", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/schwab/models/": { models: [] } });
    renderHook(() => useAiModels(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys).toContainEqual(["ai-models", "all"]);
    });
  });
});
```

- [ ] **Step 2: Run and verify pass**

Run: `docker compose exec frontend npx vitest run src/__tests__/hooks/useAiModels.test.tsx`
Expected: 4 tests passing.

- [ ] **Step 3: Coverage sweep**

Run with `--coverage` flag; verify `src/hooks/useAiModels.ts.html` is 100%.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/hooks/useAiModels.test.tsx
git commit -m "test(frontend): cover useAiModels"
```

---

## Task 12: Test `useAiUsage`

**Files:** Create `frontend/src/__tests__/hooks/useAiUsage.test.tsx`; reference `frontend/src/hooks/useAiUsage.ts`.

- [ ] **Step 1: Read the source.** Identify the fetch URL, query key, any args.
- [ ] **Step 2: Apply Phase 2 template** (loading → success, error, query-key snapshot; add mutation tests only if it's a mutation hook).

```tsx
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useAiUsage } from "@/hooks/useAiUsage";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

describe("useAiUsage", () => {
  it("returns data on success", async () => {
    mockApi({ "GET /api/schwab/usage/": { today: { claude: "0.0012" } } });
    const { result } = renderHook(() => useAiUsage(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.today.claude).toBe("0.0012");
  });
  it("sets isError on fetch failure", async () => {
    mockApiError("GET /api/schwab/usage/", 503);
    const { result } = renderHook(() => useAiUsage(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
  it("uses the documented query key", async () => {
    const client = newQueryClient();
    mockApi({ "GET /api/schwab/usage/": { today: {} } });
    renderHook(() => useAiUsage(), { wrapper: hookWrapper(client) });
    await waitFor(() => {
      const keys = client.getQueryCache().findAll().map((q) => q.queryKey);
      expect(keys.some((k) => k[0] === "ai-usage")).toBe(true);
    });
  });
});
```

- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/hooks/useAiUsage.test.tsx
git commit -m "test(frontend): cover useAiUsage"
```

---

## Task 13: Test `useChannel`

**Files:** Create `frontend/src/__tests__/hooks/useChannel.test.tsx`; reference `frontend/src/hooks/useChannel.ts`.

`useChannel` wraps the `subscribe()` from `WebSocketProvider`. Use the layered mock: stub the context value, not raw WebSocket.

- [ ] **Step 1: Read the source** to learn: what channel names does it accept, how does it expose received messages (state, callback ref)?
- [ ] **Step 2: Write the test file** using a stubbed provider:

```tsx
import { render, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WebSocketProvider, useWebSocket } from "@/realtime/WebSocketProvider";
import { useChannel } from "@/hooks/useChannel";

function makeStubbedProvider(subscribe: ReturnType<typeof vi.fn>) {
  return function Stubbed({ children }: { children: React.ReactNode }) {
    // Rebind context via actual provider + spy - or override via React.createContext mock if the real provider won't suffice.
    // The simplest path is to mock the useWebSocket export at the module level and return { subscribe }.
    return <>{children}</>;
  };
}

vi.mock("@/realtime/WebSocketProvider", async () => {
  const mod = await vi.importActual<typeof import("@/realtime/WebSocketProvider")>("@/realtime/WebSocketProvider");
  return {
    ...mod,
    useWebSocket: () => ({ subscribe: subscribeSpy }),
  };
});
const subscribeSpy = vi.fn(() => vi.fn());

describe("useChannel", () => {
  it("subscribes on mount with the given channel", () => {
    subscribeSpy.mockClear();
    renderHook(() => useChannel("thread.1", () => {}));
    expect(subscribeSpy).toHaveBeenCalledWith("thread.1", expect.any(Function));
  });
  it("invokes the unsubscribe callback on unmount", () => {
    const unsub = vi.fn();
    subscribeSpy.mockReturnValueOnce(unsub);
    const { unmount } = renderHook(() => useChannel("thread.2", () => {}));
    unmount();
    expect(unsub).toHaveBeenCalled();
  });
  it("routes received messages to the handler", () => {
    const onMessage = vi.fn();
    let capture: ((msg: unknown) => void) | null = null;
    subscribeSpy.mockImplementationOnce((_ch, handler) => {
      capture = handler;
      return () => {};
    });
    renderHook(() => useChannel("thread.3", onMessage));
    capture?.({ type: "tok", text: "hi" });
    expect(onMessage).toHaveBeenCalledWith({ type: "tok", text: "hi" });
  });
});
```

If the `useChannel` implementation uses state rather than a callback, adapt: render a component that uses the hook and assert the rendered state after `act(() => capture({...}))`.

- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/hooks/useChannel.test.tsx
git commit -m "test(frontend): cover useChannel subscribe lifecycle"
```

---

## Tasks 14–29: Remaining 16 hooks

For each hook below, follow the Phase 2 template from Task 11/12 (loading → success, error propagation, query-key snapshot; mutation-specific tests if applicable).

Each task has these steps:
1. **Read the source** (`frontend/src/hooks/<useX>.ts`) — note: URL, method, query key, args, whether it's a `useQuery` or `useMutation`.
2. **Write `frontend/src/__tests__/hooks/<useX>.test.tsx`** using the Phase 2 template. For mutations, also test `onSuccess` invalidation (spy `client.invalidateQueries`) and optimistic rollback if present.
3. **Run + coverage + commit** with message `test(frontend): cover <useX>`.

### Task 14: `useCosts`
Source: `src/hooks/useCosts.ts`. Likely exports multiple query hooks (today, by date range). Test each exported hook.

### Task 15: `useCreateConsultThread`
Source: `src/hooks/useCreateConsultThread.ts`. Mutation hook — test happy-path mutate, error, onSuccess invalidation of `["threads"]`.

### Task 16: `useCreateSnapshot`
Source: `src/hooks/useCreateSnapshot.ts`. Mutation — test mutate body shape, onSuccess invalidation of `["snapshots"]`.

### Task 17: `useHealth`
Source: `src/hooks/useHealth.ts`. Likely simple query against `/api/health/`.

### Task 18: `useMarketContext`
Source: `src/hooks/useMarketContext.ts`. Test query key includes any ticker/context args.

### Task 19: `useOhlc`
Source: `src/hooks/useOhlc.ts`. Args: ticker + range. Query-key test should assert key depends on both.

### Task 20: `usePositions`
Source: `src/hooks/usePositions.ts`. Simple query; test Schwab-not-connected path if the hook short-circuits (`enabled: false`).

### Task 21: `useProfiles`
Source: `src/hooks/useProfiles.ts`. May export list + create + update mutations; test each.

### Task 22: `useProviderConfigs`
Source: `src/hooks/useProviderConfigs.ts`. Likely query + upsert mutation — test both. For mutation, assert `onSuccess` invalidates `["provider-configs"]`.

### Task 23: `useQuotes`
Source: `src/hooks/useQuotes.ts`. Args: ticker list. Query key should include the stable ticker list (possibly sorted).

### Task 24: `useSchedules`
Source: `src/hooks/useSchedules.ts`. CRUD for observer schedules. Test list-query + create/update/delete mutations; invalidations target `["schedules"]`.

### Task 25: `useSchwabStatus`
Source: `src/hooks/useSchwabStatus.ts`. Simple query. Include a short polling-interval test only if the source sets `refetchInterval`.

### Task 26: `useSnapshot`
Source: `src/hooks/useSnapshot.ts`. By-id query; test key includes id.

### Task 27: `useThread`
Source: `src/hooks/useThread.ts`. By-id query with messages list; test key, test optimistic message insert if the hook exposes one.

### Task 28: `useWatchlist`
Source: `src/hooks/useWatchlist.ts`. By-id query.

### Task 29: `useWatchlists`
Source: `src/hooks/useWatchlists.ts`. List query + create/update mutations if present.

---

## Phase 2 close

- [ ] **Step 1: Confirm all hook tests pass**

Run: `docker compose exec frontend npx vitest run src/__tests__/hooks/`
Expected: All pass.

- [ ] **Step 2: Coverage audit for `src/hooks/`**

Run with `--coverage`; expect ≥ 80% lines across `src/hooks/`.

- [ ] **Step 3: Open Phase 2 PR**

```bash
gh pr create --title "test(frontend): phase 2 — hook coverage" --body "Covers 19 hooks with loading/error/query-key/mutation tests. Coverage ≥ 80% for src/hooks/."
```

---

## Phase 3 — Component tests (13 units)

**Phase convention:**
One test file per component at `frontend/src/__tests__/<Component>.test.tsx` (matches existing convention — no `components/` subfolder). Tests: render-with-data, render-empty/loading/error, every interactive path, accessibility queries via `getByRole`/`getByLabelText`, every conditional-rendering branch.

---

## Task 30: Test `BranchTabs` (Phase 3 opener — full worked example)

**Files:**
- Create: `frontend/src/__tests__/BranchTabs.test.tsx`
- Reference source: `frontend/src/components/BranchTabs.tsx`

Source: returns `null` when `branches.length <= 1`; otherwise renders a tab row. Clicking a tab calls `onSelect(id)`. Active tab gets emerald styling. Status suffixes: `"streaming" → "…"`, `"failed" → "✗"`, `"done" → ""`.

- [ ] **Step 1: Write the test file**

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BranchTabs from "@/components/BranchTabs";

const twoBranches = [
  { id: 1, label: "Claude", status: "streaming" as const },
  { id: 2, label: "OpenAI", status: "done" as const },
];

describe("BranchTabs", () => {
  it("renders nothing when only one branch", () => {
    const { container } = render(
      <BranchTabs branches={[{ id: 1, label: "Only", status: "done" }]} activeId={1} onSelect={() => {}} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when no branches", () => {
    const { container } = render(<BranchTabs branches={[]} activeId={null} onSelect={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a button per branch with its label", () => {
    render(<BranchTabs branches={twoBranches} activeId={1} onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: /Claude/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /OpenAI/ })).toBeInTheDocument();
  });

  it("calls onSelect with branch id on click", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<BranchTabs branches={twoBranches} activeId={1} onSelect={onSelect} />);
    await user.click(screen.getByRole("button", { name: /OpenAI/ }));
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it("marks the active tab with emerald styling", () => {
    render(<BranchTabs branches={twoBranches} activeId={2} onSelect={() => {}} />);
    const active = screen.getByRole("button", { name: /OpenAI/ });
    expect(active.className).toMatch(/border-emerald-500/);
  });

  it("shows ellipsis suffix for streaming branches", () => {
    render(<BranchTabs branches={twoBranches} activeId={1} onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: /Claude/ })).toHaveTextContent("…");
  });

  it("shows cross suffix for failed branches", () => {
    render(
      <BranchTabs
        branches={[
          { id: 1, label: "A", status: "failed" },
          { id: 2, label: "B", status: "done" },
        ]}
        activeId={1}
        onSelect={() => {}}
      />
    );
    expect(screen.getByRole("button", { name: /A/ })).toHaveTextContent("✗");
  });
});
```

- [ ] **Step 2: Run and verify pass**

Run: `docker compose exec frontend npx vitest run src/__tests__/BranchTabs.test.tsx`
Expected: 7 tests passing.

- [ ] **Step 3: Coverage sweep**

`src/components/BranchTabs.tsx.html` should be 100%.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/BranchTabs.test.tsx
git commit -m "test(frontend): cover BranchTabs render + interaction branches"
```

---

## Task 31: Test `CompareDialog`

**Files:** Create `frontend/src/__tests__/CompareDialog.test.tsx`; reference `frontend/src/components/CompareDialog.tsx`.

- [ ] **Step 1: Read source** — identify props (likely `open`, `onClose`, `onSubmit`, `availableModels`), form fields (provider+model pairs to compare), validation (min 2 pairs? unique selections?).
- [ ] **Step 2: Apply Phase 3 template.** Cover:
  - Renders dialog when `open=true`, hidden when `false`.
  - Each interactive control via `user-event`: add-pair button, remove-pair button, provider select, model select, submit, cancel.
  - Submit calls `onSubmit` with the pair array.
  - Cancel calls `onClose`.
  - Accessibility: dialog has `role="dialog"` and accessible label (`getByRole('dialog', {name:...})`); form fields have labels.

```tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import CompareDialog from "@/components/CompareDialog";

describe("CompareDialog", () => {
  it("renders when open", () => {
    render(<CompareDialog open={true} onClose={() => {}} onSubmit={() => {}} availableModels={[]} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  // + remaining ~6 tests per template
});
```

- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/CompareDialog.test.tsx
git commit -m "test(frontend): cover CompareDialog interactions"
```

---

## Task 32: Test `CostChip`

**Files:** Create `frontend/src/__tests__/CostChip.test.tsx`; reference `frontend/src/components/CostChip.tsx`.

- [ ] **Step 1: Read source** — likely renders a small USD/token chip given numeric props.
- [ ] **Step 2: Apply Phase 3 template** — render-with-data, zero value, large value (thousands formatting), className prop respected if any.
- [ ] **Step 3: Run + coverage + commit** with message `test(frontend): cover CostChip`.

---

## Task 33: Test `MarketContextStrip`

**Files:** Create `frontend/src/__tests__/MarketContextStrip.test.tsx`; reference `frontend/src/components/MarketContextStrip.tsx`.

- [ ] **Step 1: Read source** — likely consumes `useMarketContext`. Mock the hook via `vi.mock("@/hooks/useMarketContext", () => ({ useMarketContext: vi.fn() }))` and return loading/error/data states per test.
- [ ] **Step 2: Apply Phase 3 template**: render with market-open data, market-closed data, loading, error.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/MarketContextStrip.test.tsx
git commit -m "test(frontend): cover MarketContextStrip states"
```

---

## Task 34: Test `PositionsTable`

**Files:** Create `frontend/src/__tests__/PositionsTable.test.tsx`; reference `frontend/src/components/PositionsTable.tsx`.

- [ ] **Step 1: Read source** — props likely include `positions` array.
- [ ] **Step 2: Cover:** renders header + each row, empty state, P/L color class (positive green, negative red), long vs short quantity rendering.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/PositionsTable.test.tsx
git commit -m "test(frontend): cover PositionsTable"
```

---

## Task 35: Test `ProviderConfigCard`

**Files:** Create `frontend/src/__tests__/ProviderConfigCard.test.tsx`; reference `frontend/src/components/ProviderConfigCard.tsx`.

- [ ] **Step 1: Read source** — configuration form for one provider. Identify controls: enable toggle, default-model select, API-key input (write-only), daily-cap field, save button.
- [ ] **Step 2: Cover:** renders all fields from props; each field updates controlled state; save calls `onSave` with the diff; accessibility via labels; API-key field is type="password".
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/ProviderConfigCard.test.tsx
git commit -m "test(frontend): cover ProviderConfigCard form"
```

---

## Task 36: Test `ProviderModelPicker`

**Files:** Create `frontend/src/__tests__/ProviderModelPicker.test.tsx`; reference `frontend/src/components/ProviderModelPicker.tsx`.

- [ ] **Step 1: Read source** — dual select (provider + model). Model list filters by provider.
- [ ] **Step 2: Cover:** changing provider resets or filters the model list; both selects call their callbacks; loading state while model list fetches (if applicable); accessibility labels on both.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/ProviderModelPicker.test.tsx
git commit -m "test(frontend): cover ProviderModelPicker"
```

---

## Task 37: Test `QuoteCell`

**Files:** Create `frontend/src/__tests__/QuoteCell.test.tsx`; reference `frontend/src/components/QuoteCell.tsx`.

- [ ] **Step 1: Read source** — renders a single ticker's last + change.
- [ ] **Step 2: Cover:** positive change green, negative red, zero neutral, missing data fallback, formatting (decimals, currency).
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/QuoteCell.test.tsx
git commit -m "test(frontend): cover QuoteCell"
```

---

## Task 38: Test `SchwabConnectionCard`

**Files:** Create `frontend/src/__tests__/SchwabConnectionCard.test.tsx`; reference `frontend/src/components/SchwabConnectionCard.tsx`.

This component's "Connect" button navigates the browser. Stub `window.location.assign` (per spec Risk R7).

- [ ] **Step 1: Read source** — identify connect/disconnect buttons and the URL source for the OAuth start.
- [ ] **Step 2: Cover:**
  - Renders connected state with last-sync timestamp.
  - Renders disconnected state with Connect button.
  - Clicking Connect calls `window.location.assign` with the OAuth URL returned by the API (mock the hook or spy on the stub).
  - Clicking Disconnect calls the disconnect mutation.
  - Accessibility labels on buttons.

```tsx
it("navigates to OAuth URL on Connect click", async () => {
  const assign = vi.fn();
  vi.stubGlobal("location", { ...window.location, assign });
  // ... render and click ...
  expect(assign).toHaveBeenCalledWith(expect.stringContaining("schwab"));
});
```

- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/SchwabConnectionCard.test.tsx
git commit -m "test(frontend): cover SchwabConnectionCard"
```

---

## Task 39: Test `SnapshotSectionPicker`

**Files:** Create `frontend/src/__tests__/SnapshotSectionPicker.test.tsx`; reference `frontend/src/components/SnapshotSectionPicker.tsx`.

- [ ] **Step 1: Read source** — likely a multi-checkbox picker for snapshot sections (quotes, chain, news, etc.).
- [ ] **Step 2: Cover:** all sections render with labels; toggling a checkbox calls `onChange` with the updated set; "select all" / "clear" buttons if present; disabled sections if any; accessibility (each checkbox has a label).
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/SnapshotSectionPicker.test.tsx
git commit -m "test(frontend): cover SnapshotSectionPicker"
```

---

## Task 40: Test `StopButton`

**Files:** Create `frontend/src/__tests__/StopButton.test.tsx`; reference `frontend/src/components/StopButton.tsx`.

- [ ] **Step 1: Read source** — likely renders a button that POSTs to the stop endpoint via a mutation.
- [ ] **Step 2: Cover:** renders enabled while streaming, hides/disables when not streaming, calls mutation on click, shows pending state during mutation, handles error (toast/message/retry).
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/StopButton.test.tsx
git commit -m "test(frontend): cover StopButton"
```

---

## Task 41: Test `StreamingMessage`

**Files:** Create `frontend/src/__tests__/StreamingMessage.test.tsx`; reference `frontend/src/components/StreamingMessage.tsx`.

Use the layered `subscribe()` mock: `vi.mock("@/realtime/WebSocketProvider", ...)` to replace `useWebSocket` with a spy returning a subscribe function you control.

- [ ] **Step 1: Read source** — identify how message events feed rendered text, order-agnostic merge (Risk R6).
- [ ] **Step 2: Cover:**
  - Renders empty state before first event.
  - Each text-delta event appends to rendered text.
  - "done" event stops the cursor / updates status.
  - "error" event renders an error banner.
  - Subscription lifecycle: `subscribe` called with the thread channel; unsubscribe runs on unmount.

```tsx
const subscribeSpy = vi.fn();
vi.mock("@/realtime/WebSocketProvider", async () => {
  const mod = await vi.importActual<typeof import("@/realtime/WebSocketProvider")>("@/realtime/WebSocketProvider");
  return { ...mod, useWebSocket: () => ({ subscribe: subscribeSpy }) };
});

// Test:
let capture: ((msg: unknown) => void) | null = null;
subscribeSpy.mockImplementation((_ch, h) => { capture = h; return () => {}; });
render(<StreamingMessage threadId={1} messageId={5} />);
act(() => capture?.({ type: "text_delta", text: "Hello " }));
act(() => capture?.({ type: "text_delta", text: "world" }));
act(() => capture?.({ type: "done" }));
expect(screen.getByText(/Hello world/)).toBeInTheDocument();
```

- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/StreamingMessage.test.tsx
git commit -m "test(frontend): cover StreamingMessage event merging"
```

---

## Task 42: Test `WatchlistTable`

**Files:** Create `frontend/src/__tests__/WatchlistTable.test.tsx`; reference `frontend/src/components/WatchlistTable.tsx`.

- [ ] **Step 1: Read source** — probably iterates tickers and renders `QuoteCell` per row; may include add/remove ticker controls.
- [ ] **Step 2: Cover:** renders row per ticker; empty state; remove-ticker button fires callback; add-ticker input + submit fires callback with the new symbol (trimmed, upper-cased if applicable); accessibility (rows as `<tr role="row">`, table has caption/heading).
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/WatchlistTable.test.tsx
git commit -m "test(frontend): cover WatchlistTable"
```

---

## Phase 3 close

- [ ] **Step 1: Confirm all component tests pass**

Run: `docker compose exec frontend npx vitest run src/__tests__/`
Expected: All Phase 1–3 tests pass.

- [ ] **Step 2: Coverage audit**

Run with `--coverage`; expect ≥ 75% for `src/components/`.

- [ ] **Step 3: Open Phase 3 PR**

```bash
gh pr create --title "test(frontend): phase 3 — component coverage" --body "Covers 13 components with rendering, interaction, and a11y tests. Coverage ≥ 75% for src/components/."
```

---

## Phase 4 — Page tests (9 units)

**Phase convention:**
One test file per page at `frontend/src/__tests__/<Page>.test.tsx`. Use `renderWithProviders` with the `routes` option when `useNavigate` / `Link` matter; use the `LocationProbe` helper to assert URL changes rather than spying on `useNavigate` (Risk R3). Every fetch the page issues on mount must be declared in `mockApi({...})`.

---

## Task 43: Test `CostsPage` (Phase 4 opener — full worked example)

**Files:**
- Create: `frontend/src/__tests__/CostsPage.test.tsx`
- Reference source: `frontend/src/pages/CostsPage.tsx`

Source: loading → renders "Loading…"; success → renders total cost + one row per provider in `data.by_provider`. Depends on `useCostsToday` which hits `/api/costs/today/` (verify URL by opening `src/hooks/useCosts.ts`).

- [ ] **Step 1: Write the test file**

```tsx
import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import CostsPage from "@/pages/CostsPage";
import { mockApi, mockApiError, renderWithProviders } from "./testUtils";

const okResp = {
  total_usd: "0.1234",
  by_provider: [
    { provider: "claude", runs: 3, input_tokens: 1200, cached_tokens: 200, output_tokens: 800, cost_usd: "0.0500" },
    { provider: "openai", runs: 2, input_tokens: 900, cached_tokens: 0, output_tokens: 500, cost_usd: "0.0734" },
  ],
};

describe("CostsPage", () => {
  it("shows loading before data arrives", () => {
    mockApi({ "GET /api/costs/today/": okResp });
    renderWithProviders(<CostsPage />);
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
  });

  it("renders the total cost after data loads", async () => {
    mockApi({ "GET /api/costs/today/": okResp });
    renderWithProviders(<CostsPage />);
    await waitFor(() => expect(screen.getByText(/0\.1234/)).toBeInTheDocument());
  });

  it("renders one row per provider with formatted counts", async () => {
    mockApi({ "GET /api/costs/today/": okResp });
    renderWithProviders(<CostsPage />);
    await waitFor(() => expect(screen.getByText(/claude/i)).toBeInTheDocument());
    expect(screen.getByText(/openai/i)).toBeInTheDocument();
    expect(screen.getByText("1,200")).toBeInTheDocument();
    expect(screen.getByText(/0\.0500/)).toBeInTheDocument();
  });

  it("renders zero-cost fallback when total_usd is missing", async () => {
    mockApi({ "GET /api/costs/today/": { by_provider: [] } });
    renderWithProviders(<CostsPage />);
    await waitFor(() => expect(screen.getByText(/0\.0000/)).toBeInTheDocument());
  });

  it("renders empty body when by_provider is absent", async () => {
    mockApi({ "GET /api/costs/today/": {} });
    renderWithProviders(<CostsPage />);
    await waitFor(() => expect(screen.getByRole("columnheader", { name: /Provider/ })).toBeInTheDocument());
    // No data rows rendered
    expect(screen.queryByText(/claude/i)).not.toBeInTheDocument();
  });

  it("renders an error state when the request fails", async () => {
    mockApiError("GET /api/costs/today/", 500);
    renderWithProviders(<CostsPage />);
    // Default isLoading ends with isError; page remains in its initial guard.
    // If CostsPage doesn't render an error UI today, the failing test drives a small fix — open a follow-up if needed.
    await waitFor(() => expect(screen.queryByText(/Loading/)).not.toBeInTheDocument());
  });
});
```

If the current `CostsPage` doesn't render an error state (source only handles `isLoading`), the last test is a soft assertion; it documents the gap. If you believe an error state is warranted, open a follow-up TODO in the plan's Risk register — do not refactor in this PR.

- [ ] **Step 2: Run and verify pass**

Run: `docker compose exec frontend npx vitest run src/__tests__/CostsPage.test.tsx`
Expected: All tests pass.

- [ ] **Step 3: Coverage sweep**

`src/pages/CostsPage.tsx.html` ≥ 90%.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/CostsPage.test.tsx
git commit -m "test(frontend): cover CostsPage loading/success/empty/error"
```

---

## Task 44: Test `Dashboard`

**Files:** Create `frontend/src/__tests__/Dashboard.test.tsx`; reference `frontend/src/pages/Dashboard.tsx`.

Dashboard fires many concurrent queries — market context, quotes, positions, maybe health/schedule summary. Mock every fetch it issues.

- [ ] **Step 1: Read source** — list every hook/fetch on mount. Identify primary visible content per state.
- [ ] **Step 2: Apply Phase 4 template.** Cover:
  - Initial render with all queries mocked → primary cards/sections visible.
  - Loading skeleton path for at least the slowest query (delay its resolution).
  - Error path for the primary query.
  - Key interaction: e.g. clicking a ticker navigates to its market page (use `routes:[{path:'/',element:<Dashboard/>},{path:'/market/:ticker',element:<LocationProbe .../>}]` and assert the path).
  - NotificationBell presence (rendered by Dashboard per CLAUDE.md).
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/Dashboard.test.tsx
git commit -m "test(frontend): cover Dashboard composition + navigation"
```

---

## Task 45: Test `ProfilesPage`

**Files:** Create `frontend/src/__tests__/ProfilesPage.test.tsx`; reference `frontend/src/pages/ProfilesPage.tsx`.

- [ ] **Step 1: Read source** — CRUD UI for trading profiles.
- [ ] **Step 2: Apply Phase 4 template.** Cover: list render, empty state, create-profile form submit, edit existing, delete with confirmation if present, error toasts on failed mutation.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/ProfilesPage.test.tsx
git commit -m "test(frontend): cover ProfilesPage CRUD"
```

---

## Task 46: Test `Settings`

**Files:** Create `frontend/src/__tests__/Settings.test.tsx`; reference `frontend/src/pages/Settings.tsx`.

Per Risk R8, if the single file grows past ~300 lines, split into `Settings.providers.test.tsx`, `Settings.credentials.test.tsx`, `Settings.profiles.test.tsx`, etc.

- [ ] **Step 1: Read source** — inventory the sections (provider configs, credentials, profile defaults).
- [ ] **Step 2: Apply Phase 4 template per section.** Each section: initial render, form interaction, save fires correct mutation body, error state. Schwab OAuth triggers use `window.location.assign` stub.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/Settings*.test.tsx
git commit -m "test(frontend): cover Settings sections"
```

---

## Task 47: Test `SnapshotComposerPage`

**Files:** Create `frontend/src/__tests__/SnapshotComposerPage.test.tsx`; reference `frontend/src/pages/SnapshotComposerPage.tsx`.

- [ ] **Step 1: Read source** — form for new snapshot (objective, section picker, tickers, profile, AI provider/model).
- [ ] **Step 2: Apply Phase 4 template.** Cover: initial render with defaults, toggling `SnapshotSectionPicker`, entering tickers, submit fires `useCreateSnapshot` with the right body, post-submit navigation to the new thread's page (assert via `LocationProbe`).
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/SnapshotComposerPage.test.tsx
git commit -m "test(frontend): cover SnapshotComposerPage submit + navigation"
```

---

## Task 48: Test `ThreadDetailPage`

**Files:** Create `frontend/src/__tests__/ThreadDetailPage.test.tsx`; reference `frontend/src/pages/ThreadDetailPage.tsx`.

- [ ] **Step 1: Read source** — renders thread messages + compose box + possibly `CompareDialog` + `StopButton`. Uses `useThread` + streaming via `useChannel`/`StreamingMessage`.
- [ ] **Step 2: Apply Phase 4 template.** Cover: list of prior messages renders; send-message mutation fires; clicking compare opens dialog; stop button appears while streaming; branch-tab navigation when compare response arrives.

Mock the realtime layer via the `useWebSocket` stub from Task 13.

- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/ThreadDetailPage.test.tsx
git commit -m "test(frontend): cover ThreadDetailPage thread interactions"
```

---

## Task 49: Test `ThreadsPage`

**Files:** Create `frontend/src/__tests__/ThreadsPage.test.tsx`; reference `frontend/src/pages/ThreadsPage.tsx`.

- [ ] **Step 1: Read source** — list/index of threads.
- [ ] **Step 2: Apply Phase 4 template.** List render, empty, click navigates to `/threads/:id` (assert path via `LocationProbe`), error state.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/ThreadsPage.test.tsx
git commit -m "test(frontend): cover ThreadsPage listing + navigation"
```

---

## Task 50: Test `WatchlistDetail`

**Files:** Create `frontend/src/__tests__/WatchlistDetail.test.tsx`; reference `frontend/src/pages/WatchlistDetail.tsx`.

- [ ] **Step 1: Read source** — loads one watchlist, renders `WatchlistTable`.
- [ ] **Step 2: Apply Phase 4 template.** Loading, success (table renders), error, add-ticker flow, delete-watchlist flow + navigation back.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/WatchlistDetail.test.tsx
git commit -m "test(frontend): cover WatchlistDetail"
```

---

## Task 51: Test `WatchlistsList`

**Files:** Create `frontend/src/__tests__/WatchlistsList.test.tsx`; reference `frontend/src/pages/WatchlistsList.tsx`.

- [ ] **Step 1: Read source** — list of all watchlists with create.
- [ ] **Step 2: Apply Phase 4 template.** List render, empty, create new (mutation fires, invalidates list), click a watchlist navigates to `/watchlists/:id`.
- [ ] **Step 3: Run + coverage + commit.**

```bash
git add frontend/src/__tests__/WatchlistsList.test.tsx
git commit -m "test(frontend): cover WatchlistsList"
```

---

## Phase 4 close

- [ ] **Step 1: Confirm all page tests pass.** `docker compose exec frontend npx vitest run src/__tests__/`. All tests green.
- [ ] **Step 2: Coverage audit.** Expect ≥ 75% for `src/pages/`.
- [ ] **Step 3: Open Phase 4 PR.**

```bash
gh pr create --title "test(frontend): phase 4 — page coverage" --body "Covers 9 pages with route-level composition + interaction tests."
```

---

## Phase 5 — Realtime

---

## Task 52: Test `WebSocketProvider`

**Files:**
- Create: `frontend/src/__tests__/realtime/WebSocketProvider.test.tsx`
- Reference source: `frontend/src/realtime/WebSocketProvider.tsx`, `frontend/src/realtime/subscriptions.ts`

Uses `installFakeWebSocket()`.

- [ ] **Step 1: Write the test file**

```tsx
import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";
import { WebSocketProvider, useWebSocket } from "@/realtime/WebSocketProvider";
import { installFakeWebSocket, type FakeWebSocketController } from "../testUtils";

let fake: FakeWebSocketController;

function TestConsumer({ channel, onMsg }: { channel: string; onMsg: (m: unknown) => void }) {
  const { subscribe } = useWebSocket();
  useEffect(() => subscribe(channel, onMsg), [subscribe, channel, onMsg]);
  return null;
}

beforeEach(() => {
  fake = installFakeWebSocket();
});
afterEach(() => {
  fake.restore();
});

describe("WebSocketProvider", () => {
  it("opens a socket with the thread path on first subscribe", () => {
    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.42" onMsg={() => {}} />
      </WebSocketProvider>
    );
    expect(fake.sockets).toHaveLength(1);
    expect(fake.sockets[0].url).toMatch(/\/ws\/threads\/42\/$/);
  });

  it("opens a snapshot socket for snapshot.X channel", () => {
    render(
      <WebSocketProvider>
        <TestConsumer channel="snapshot.7" onMsg={() => {}} />
      </WebSocketProvider>
    );
    expect(fake.sockets[0].url).toMatch(/\/ws\/snapshots\/7\/$/);
  });

  it("routes parsed JSON messages to subscribers of that channel", () => {
    const handler = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={handler} />
      </WebSocketProvider>
    );
    fake.sockets[0].emitMessage({ type: "tok", text: "hi" });
    expect(handler).toHaveBeenCalledWith({ type: "tok", text: "hi" });
  });

  it("does not deliver thread.1 messages to thread.2 subscribers", () => {
    const one = vi.fn(); const two = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={one} />
        <TestConsumer channel="thread.2" onMsg={two} />
      </WebSocketProvider>
    );
    fake.find("/ws/threads/1/")!.emitMessage({ x: 1 });
    expect(one).toHaveBeenCalledWith({ x: 1 });
    expect(two).not.toHaveBeenCalled();
  });

  it("ignores malformed JSON payloads without crashing", () => {
    const handler = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={handler} />
      </WebSocketProvider>
    );
    // Directly push a raw non-JSON string:
    (fake.sockets[0].listeners.message ?? []).forEach((l) => l(new MessageEvent("message", { data: "not json" })));
    expect(handler).not.toHaveBeenCalled();
  });

  it("closes the socket when the last subscriber unsubscribes", () => {
    const { unmount } = render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={() => {}} />
      </WebSocketProvider>
    );
    const closeSpy = vi.spyOn(fake.sockets[0], "close");
    unmount();
    expect(closeSpy).toHaveBeenCalled();
  });

  it("throws when useWebSocket is called outside the provider", () => {
    function Bad() { useWebSocket(); return null; }
    expect(() => render(<Bad />)).toThrow(/useWebSocket must be used inside WebSocketProvider/);
  });

  it("throws on unknown channel prefix", () => {
    expect(() => render(
      <WebSocketProvider>
        <TestConsumer channel="unknown.1" onMsg={() => {}} />
      </WebSocketProvider>
    )).toThrow(/Unknown channel/);
  });
});
```

Note: if `useEffect` in `TestConsumer` is awkward, define it via a ref pattern or inline via `useMemo`. The shape must survive mount → dispatch → unmount in one test render.

- [ ] **Step 2: Run and verify pass**

Run: `docker compose exec frontend npx vitest run src/__tests__/realtime/WebSocketProvider.test.tsx`
Expected: 8 tests passing.

- [ ] **Step 3: Coverage sweep**

`src/realtime/WebSocketProvider.tsx.html` ≥ 90%. If `useEffect` unmount cleanup branch isn't green, add a test that unmounts the provider while a subscription is active.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/__tests__/realtime/WebSocketProvider.test.tsx
git commit -m "test(frontend): cover WebSocketProvider broker + socket lifecycle"
```

---

## Task 53: Realtime audit — migrate existing WS tests to helpers

**Files:**
- Modify: `frontend/src/__tests__/NotificationBell.test.tsx`
- Modify: `frontend/src/__tests__/ObserverTimelinePage.test.tsx`

Spec §Decisions #5 + Risk Q-B: these existing tests may mock WebSocket via ad-hoc code. Migrate each to use `installFakeWebSocket()` (if they mount `WebSocketProvider`) or the `vi.mock("@/realtime/WebSocketProvider", ...)` stub (if they rely on `useWebSocket` directly). Functional behavior of the tests must not change.

- [ ] **Step 1: Read `NotificationBell.test.tsx`**

Identify the current mocking mechanism. Map each assertion to the new helper equivalent.

- [ ] **Step 2: Refactor `NotificationBell.test.tsx`**

Replace ad-hoc `WebSocket` stubbing with `installFakeWebSocket()` in `beforeEach`/`afterEach`; push messages via `fake.find('/ws/...').emitMessage(...)`. All existing assertions must still pass.

- [ ] **Step 3: Run `NotificationBell.test.tsx`** — verify still passes.

Run: `docker compose exec frontend npx vitest run src/__tests__/NotificationBell.test.tsx`

- [ ] **Step 4: Repeat Steps 1-3 for `ObserverTimelinePage.test.tsx`.**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/__tests__/NotificationBell.test.tsx frontend/src/__tests__/ObserverTimelinePage.test.tsx
git commit -m "test(frontend): migrate realtime consumer tests to installFakeWebSocket"
```

---

## Task 54: Final coverage baseline + Phase 5 PR

- [ ] **Step 1: Run the full suite**

Run: `docker compose exec frontend npx vitest run`
Expected: All tests pass; total runtime ≤ 25s.

- [ ] **Step 2: Run with coverage and record the numbers**

Run: `docker compose exec frontend npx vitest run --coverage`
Record per-folder line coverage in the Phase 5 PR description:
- `src/api/` : __%
- `src/hooks/` : __%
- `src/components/` : __%
- `src/pages/` : __%
- `src/realtime/` : __%

- [ ] **Step 3: Sanity-check against spec Risk R9**

Expected ranges: api 85–90%, hooks 80–85%, pages/components 75–80%. Below expected for any folder → investigate the lowest-covered file and add a test before opening the PR.

- [ ] **Step 4: Open Phase 5 PR**

```bash
gh pr create --title "test(frontend): phase 5 — realtime + coverage baseline" --body "$(cat <<'EOF'
## Summary
- New `WebSocketProvider` test suite using `installFakeWebSocket()` helper
- Migrates `NotificationBell` + `ObserverTimelinePage` tests to the same helper
- Closes the frontend test coverage expansion (spec: 2026-04-18-frontend-test-coverage-design.md)

## Coverage (from `make test-cov`)
- src/api/     : __%
- src/hooks/   : __%
- src/components/ : __%
- src/pages/   : __%
- src/realtime/ : __%

## Test plan
- [ ] `make test` passes, full suite ≤ 25s
- [ ] `make test-cov` generates an HTML report at `frontend/coverage/`

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 5: Final verification**

Run `make check` inside the repo to confirm the whole CI gate passes (lint + test across backend + frontend).

---

## Summary

This plan delivers thorough vitest coverage for 51 untested units across the frontend, phased into 5 PRs. Every task is self-contained: exact file paths, exact mock helper calls, commit messages, and coverage targets. Full suite remains ≤ 25s after completion; coverage reporter lands as report-only visibility, no CI gate added.
