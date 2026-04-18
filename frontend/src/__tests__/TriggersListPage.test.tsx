import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import TriggersListPage from "../pages/TriggersListPage";
import { ToastProvider } from "@/hooks/useToast";

const TRIGGERS = [
  {
    id: 1, name: "SPY>550", profile: 1,
    condition: { metric: "price", ticker: "SPY", op: ">", value: 550 },
    cooldown_seconds: 1800, enabled: true, last_fired_at: null, firings_count: 3,
    created_at: "2026-04-18T00:00:00Z", updated_at: "2026-04-18T00:00:00Z",
  },
];

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/triggers/") && (!init || init.method === "GET" || !init.method)) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(TRIGGERS) });
    }
    if (init?.method === "PATCH") {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ...TRIGGERS[0], enabled: false }) });
    }
    if (init?.method === "DELETE") {
      return Promise.resolve({ ok: true, status: 204, json: () => Promise.resolve({}) });
    }
    if (init?.method === "POST" && url.includes("/fire/")) {
      return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ task_id: "t" }) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  }) as never;
});

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("TriggersListPage", () => {
  it("renders the list with names and firings_count", async () => {
    render(
      <QueryClientProvider client={qc()}>
        <ToastProvider><MemoryRouter><TriggersListPage /></MemoryRouter></ToastProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("SPY>550")).toBeInTheDocument());
    expect(screen.getByText(/3 firings/i)).toBeInTheDocument();
  });

  it("fires manual fire on button click (after confirm)", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(
      <QueryClientProvider client={qc()}>
        <ToastProvider><MemoryRouter><TriggersListPage /></MemoryRouter></ToastProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("SPY>550")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /fire now/i }));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      const calls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls;
      expect(calls.some((c) => typeof c[0] === "string" && c[0].includes("/fire/"))).toBe(true);
    });
    confirmSpy.mockRestore();
  });

  it("shows empty state when no triggers", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
    ) as never;
    render(
      <QueryClientProvider client={qc()}>
        <ToastProvider><MemoryRouter><TriggersListPage /></MemoryRouter></ToastProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText(/no triggers yet/i)).toBeInTheDocument());
  });
});
