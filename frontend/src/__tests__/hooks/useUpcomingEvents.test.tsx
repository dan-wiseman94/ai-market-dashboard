import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "@/api/market";
import { useUpcomingEvents } from "@/hooks/useUpcomingEvents";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useUpcomingEvents", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("fetches upcoming events for the given tickers", async () => {
    const spy = vi.spyOn(api, "fetchUpcomingEvents").mockResolvedValue({
      earnings: [{ kind: "earnings", ticker: "NVDA", title: "NVDA earnings",
        event_time: "2026-05-29T21:00:00Z", days_until: 2, when_hint: "amc",
        impact: "high", detail: {} }],
      macro: [],
    });
    const { result } = renderHook(() => useUpcomingEvents(["NVDA"]), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.earnings[0].ticker).toBe("NVDA");
    expect(spy).toHaveBeenCalledWith(["NVDA"], 14);
  });
});
