import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as api from "@/api/briefing";
import { useLatestBriefing } from "@/hooks/useBriefing";
import { hookWrapper } from "../testUtils";

describe("useLatestBriefing", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("fetches the latest briefing", async () => {
    vi.spyOn(api, "fetchLatestBriefing").mockResolvedValue({
      id: 1, status: "ready", created_at: "2026-05-28T12:00:00Z", scheduled_date: null,
      data: { theses: [], events: { earnings: [], macro: [] }, triggers: [], news: [], market: {}, since: "x" },
      synthesis_text: "Lead with NVDA.", synthesis_status: "done", snapshot: null,
    });
    const { result } = renderHook(() => useLatestBriefing(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.synthesis_text).toBe("Lead with NVDA.");
  });
});
