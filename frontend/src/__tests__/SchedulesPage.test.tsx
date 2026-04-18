import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SchedulesPage from "../pages/SchedulesPage";

const SCHEDULES = [
  {
    id: 1, name: "Hourly", profile: 1, enabled: true, market_hours_only: true,
    objective_template: "", override_provider: "", override_model: "",
    default_includes: [], default_watchlist_tickers: [],
    last_fired_at: null, cron_display: "0 * * * *",
    created_at: "2026-04-17T00:00:00Z", updated_at: "2026-04-17T00:00:00Z",
  },
];

beforeEach(() => {
  globalThis.fetch = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/observer/schedules/") && (!init || init.method === "GET" || !init.method)) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SCHEDULES) });
    }
    if (url.startsWith("/api/profiles/")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 1, name: "P", default_includes: [] }]) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  }) as never;
});

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("SchedulesPage", () => {
  it("renders schedules list", async () => {
    render(<QueryClientProvider client={qc()}><SchedulesPage /></QueryClientProvider>);
    await waitFor(() => expect(screen.getByText("Hourly")).toBeInTheDocument());
    expect(screen.getByText(/0 \* \* \* \*/)).toBeInTheDocument();
  });

  it("renders empty state when no schedules", async () => {
    globalThis.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
    ) as never;
    render(<QueryClientProvider client={qc()}><SchedulesPage /></QueryClientProvider>);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
  });

  it("submits selected preset cron via create form", async () => {
    const postSpy = vi.fn((_url: string, _init: RequestInit) =>
      Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({}) }),
    );
    globalThis.fetch = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST" && url.startsWith("/api/observer/schedules/")) {
        return postSpy(url, init);
      }
      if (url.startsWith("/api/observer/schedules/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
      }
      if (url.startsWith("/api/profiles/")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve([{ id: 1, name: "P", default_includes: [] }]) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    }) as never;

    render(<QueryClientProvider client={qc()}><SchedulesPage /></QueryClientProvider>);
    await waitFor(() => expect(screen.getByText(/no schedules/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /new schedule/i }));
    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "TestSched" } });
    // Default preset is "Every 15 minutes"
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));

    await waitFor(() => expect(postSpy).toHaveBeenCalled());
    const body = JSON.parse((postSpy.mock.calls[0][1] as RequestInit).body as string);
    expect(body.name).toBe("TestSched");
    expect(body.cron).toBe("*/15 * * * *");
    expect(body.profile).toBe(1);
  });
});
