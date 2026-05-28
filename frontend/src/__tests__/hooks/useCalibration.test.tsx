import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as client from "@/api/client";
import { useCalibration } from "@/hooks/useAnalytics";
import { hookWrapper } from "../testUtils";

describe("useCalibration", () => {
  beforeEach(() => vi.restoreAllMocks());
  it("fetches calibration for the horizon", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue({
      horizon: 30, scored: 1, attributable: 0,
      thesis: { buckets: [], brier: 0.1, prob_map: {}, overall: { scored: 1, hit_rate: 1, correct: 1, incorrect: 0, mixed: 0, inconclusive: 0, avg_forward_return_pct: 5 }, by_direction: {} },
      provider: [],
    });
    const { result } = renderHook(() => useCalibration(90, 30), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.horizon).toBe(30);
    expect(spy).toHaveBeenCalledWith(expect.stringContaining("/api/analytics/calibration/?horizon=30"));
    expect(spy).toHaveBeenCalledWith(expect.stringContaining("&start="));
  });
});
