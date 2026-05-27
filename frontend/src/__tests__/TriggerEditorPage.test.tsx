import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TriggerEditorPage from "../pages/TriggerEditorPage";

const PROFILES = [{ id: 1, name: "Default", default_includes: [] }];

function mockFetch(responder: (url: string, init?: RequestInit) => unknown) {
  globalThis.fetch = vi.fn((url: string, init?: RequestInit) =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(responder(url, init)) }),
  ) as never;
}

beforeEach(() => {
  mockFetch((url) => {
    if (url.startsWith("/api/profiles/")) return PROFILES;
    if (url.includes("/evaluate/")) return { matched: true, values: { "price:SPY": 551.2 }, missing: [] };
    return {};
  });
});

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

function renderAt(path: string, routePath: string) {
  return render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={<TriggerEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Like renderAt but also mounts a /triggers landing route so we can assert navigation. */
function renderFlow(path: string, routePath: string) {
  return render(
    <QueryClientProvider client={qc()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={routePath} element={<TriggerEditorPage />} />
          <Route path="/triggers" element={<div>TRIGGERS LIST</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

type FetchCall = [string, RequestInit | undefined];
function fetchCalls(): FetchCall[] {
  return (globalThis.fetch as unknown as { mock: { calls: FetchCall[] } }).mock.calls;
}
function lastCall(predicate: (url: string, init?: RequestInit) => boolean): FetchCall | undefined {
  return [...fetchCalls()].reverse().find(([u, init]) => predicate(u, init));
}

describe("TriggerEditorPage", () => {
  it("renders create form on /triggers/new", async () => {
    renderAt("/triggers/new", "/triggers/new");
    await waitFor(() => expect(screen.getByText(/New trigger/i)).toBeInTheDocument());
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
  });

  it("live preview POSTs to /evaluate/ after debounce and shows YES", async () => {
    renderAt("/triggers/new", "/triggers/new");
    await waitFor(() => expect(screen.getByLabelText(/name/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "SPY" } });
    // Wait for debounce + query to resolve (real timers, 600ms debounce)
    await waitFor(
      () => expect(screen.getByText(/YES/i)).toBeInTheDocument(),
      { timeout: 3000 },
    );
  });

  it("Cancel navigates back to the triggers list", async () => {
    renderFlow("/triggers/new", "/triggers/new");
    await screen.findByLabelText(/name/i);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(await screen.findByText("TRIGGERS LIST")).toBeInTheDocument();
  });

  it("disables Save until a name is entered, then creates and navigates", async () => {
    renderFlow("/triggers/new", "/triggers/new");
    await screen.findByLabelText(/name/i);
    const save = screen.getByRole("button", { name: /save/i });
    // Name is empty on first render → Save is disabled regardless of profile.
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "SPY breakout" } });
    // Cooldown's label isn't htmlFor-associated and RuleBuilder also renders number
    // inputs, so target the cooldown field by its unique default value (1800).
    fireEvent.change(screen.getByDisplayValue("1800"), { target: { value: "60" } });
    fireEvent.click(screen.getByLabelText(/enabled/i)); // toggle Enabled off
    await waitFor(() => expect(save).toBeEnabled());

    fireEvent.click(save);
    expect(await screen.findByText("TRIGGERS LIST")).toBeInTheDocument();

    const post = lastCall((u, init) => u === "/api/triggers/" && init?.method === "POST");
    expect(post).toBeDefined();
    const body = JSON.parse(post![1]!.body as string);
    expect(body).toMatchObject({ name: "SPY breakout", profile: 1, cooldown_seconds: 60, enabled: false });
  });

  it("seeds the form from an existing trigger and PATCHes on save", async () => {
    const TRIGGER = {
      id: 5, name: "SPY breakout", profile: 1, firings_count: 3,
      condition: { all: [{ metric: "price", ticker: "SPY", op: ">", value: 500 }] },
      cooldown_seconds: 1800, enabled: true,
    };
    mockFetch((url) => {
      if (url.startsWith("/api/profiles/")) return PROFILES;
      if (url.includes("/evaluate/")) return { matched: false, values: {}, missing: [] };
      if (url === "/api/triggers/" || url.startsWith("/api/triggers/?")) return [TRIGGER];
      return {};
    });
    renderFlow("/triggers/5", "/triggers/:id");

    // Heading + name input are seeded from the loaded trigger.
    expect(await screen.findByDisplayValue("SPY breakout")).toBeInTheDocument();
    expect(screen.getByText(/Edit trigger: SPY breakout/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "SPY breakout v2" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    expect(await screen.findByText("TRIGGERS LIST")).toBeInTheDocument();

    const patch = lastCall((u, init) => u === "/api/triggers/5/" && init?.method === "PATCH");
    expect(patch).toBeDefined();
    expect(JSON.parse(patch![1]!.body as string).name).toBe("SPY breakout v2");
  });

  it("switches between Condition, Firings, and Backtest tabs in edit mode", async () => {
    const TRIGGER = {
      id: 5, name: "SPY breakout", profile: 1, firings_count: 0,
      condition: { all: [{ metric: "price", ticker: "SPY", op: ">", value: 500 }] },
      cooldown_seconds: 1800, enabled: true,
    };
    mockFetch((url) => {
      if (url.startsWith("/api/profiles/")) return PROFILES;
      if (url.includes("/evaluate/")) return { matched: false, values: {}, missing: [] };
      if (url.includes("/firings/")) return { results: [] };
      if (url.startsWith("/api/triggers/")) return [TRIGGER];
      return {};
    });
    renderFlow("/triggers/5", "/triggers/:id");
    await screen.findByDisplayValue("SPY breakout");

    fireEvent.click(screen.getByRole("button", { name: /firings/i }));
    expect(await screen.findByText(/no firings yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /backtest/i }));
    expect(screen.getByRole("button", { name: /run backtest/i })).toBeInTheDocument();
  });

  it("runs a backtest and renders the match count", async () => {
    const TRIGGER = {
      id: 5, name: "SPY breakout", profile: 1, firings_count: 0,
      condition: { all: [{ metric: "price", ticker: "SPY", op: ">", value: 500 }] },
      cooldown_seconds: 1800, enabled: true,
    };
    mockFetch((url) => {
      if (url.startsWith("/api/profiles/")) return PROFILES;
      if (url.includes("/evaluate/")) return { matched: false, values: {}, missing: [] };
      if (url.includes("/backtest/")) {
        return { match_count: 2, matches: [
          { ts: "2026-03-01T14:30:00Z", values: { "price:SPY": 551.2, "_prior:price:SPY": 540 } },
          { ts: "2026-03-02T14:30:00Z", values: { "price:SPY": 552.0 } },
        ] };
      }
      if (url.startsWith("/api/triggers/")) return [TRIGGER];
      return {};
    });
    renderFlow("/triggers/5", "/triggers/:id");
    await screen.findByDisplayValue("SPY breakout");

    fireEvent.click(screen.getByRole("button", { name: /backtest/i }));
    fireEvent.click(screen.getByRole("button", { name: /run backtest/i }));

    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByText(/matches/i)).toBeInTheDocument();
    // The _prior: key is filtered out of the rendered match line.
    expect(screen.getByText(/price:SPY=551\.2/)).toBeInTheDocument();
    const post = lastCall((u, init) => u === "/api/triggers/backtest/" && init?.method === "POST");
    expect(post).toBeDefined();
  });
});
