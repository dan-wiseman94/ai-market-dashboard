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
});
