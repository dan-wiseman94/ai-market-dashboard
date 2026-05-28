import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "@/api/briefing";
import { useLatestBriefing } from "@/hooks/useBriefing";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useLatestBriefing", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("fetches the latest briefing", async () => {
    vi.spyOn(api, "fetchLatestBriefing").mockResolvedValue({
      id: 1, status: "ready", created_at: "2026-05-28T12:00:00Z", scheduled_date: null,
      data: { theses: [], events: { earnings: [], macro: [] }, triggers: [], news: [], market: {}, since: "x" },
      synthesis_text: "Lead with NVDA.", synthesis_status: "done", snapshot: null,
    });
    const { result } = renderHook(() => useLatestBriefing(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.synthesis_text).toBe("Lead with NVDA.");
  });
});
