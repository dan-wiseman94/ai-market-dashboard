import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Snapshot } from "@/api/snapshots";
import { useCreateSnapshot } from "@/hooks/useCreateSnapshot";
import { hookWrapper, mockApi, mockApiError } from "../testUtils";

const snapshotFixture: Snapshot = {
  id: 5,
  profile_id: 2,
  objective: "Assess morning open",
  notes: "",
  manual_positions: "",
  candidate_positions: "",
  status: "pending",
  includes: ["quotes"],
  source: "manual",
  captured_at: "2026-05-17T09:30:00Z",
  sections: [],
};

describe("useCreateSnapshot", () => {
  it("returns the created Snapshot on success", async () => {
    mockApi({ "POST /api/snapshots/": snapshotFixture });
    const { result } = renderHook(() => useCreateSnapshot(), {
      wrapper: hookWrapper(),
    });
    let data: Snapshot | undefined;
    await act(async () => {
      data = await result.current.mutateAsync({ profile_id: 2 });
    });
    expect(data?.id).toBe(5);
    expect(data?.status).toBe("pending");
  });

  it("sends the full CreateSnapshotBody including optional fields", async () => {
    const { calls } = mockApi({ "POST /api/snapshots/": snapshotFixture });
    const { result } = renderHook(() => useCreateSnapshot(), {
      wrapper: hookWrapper(),
    });
    const body = {
      profile_id: 2,
      objective: "Assess morning open",
      notes: "note",
      includes: ["quotes", "ohlc"],
      watchlist_tickers: ["AAPL"],
      ohlc_ticker: "AAPL",
      ohlc_timeframe: "5m",
      ohlc_bars: 100,
      image_ids: [3],
    };
    await act(async () => {
      await result.current.mutateAsync(body);
    });
    expect(calls[0].body).toMatchObject(body);
  });

  it("isError when the request fails", async () => {
    mockApiError("POST /api/snapshots/", 400);
    const { result } = renderHook(() => useCreateSnapshot(), {
      wrapper: hookWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ profile_id: 2 }).catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
