import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as client from "@/api/client";
import { useTrackRecord } from "@/hooks/useAnalytics";
import { hookWrapper } from "../testUtils";

const MOCK_RECORD = {
  ticker: "NVDA",
  closed_n: 3,
  counts: { win: 2, loss: 1, scratch: 0, invalidated: 0 },
  hit_rate: 0.6667,
  last: { direction: "bullish", conviction: 4, status: "closed_win" },
  slice: { direction: "bullish", conviction: 4, correct: 2, n: 2, hit_rate: 1.0 },
};

const MOCK_RESPONSE = {
  ticker: "NVDA",
  available: true,
  record: MOCK_RECORD,
};

describe("useTrackRecord", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns track record data and requests ticker in URL", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue(MOCK_RESPONSE);
    const { result } = renderHook(
      () => useTrackRecord("NVDA"),
      { wrapper: hookWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.available).toBe(true);
    expect(result.current.data?.record?.ticker).toBe("NVDA");
    expect(result.current.data?.record?.counts.win).toBe(2);
    expect(result.current.data?.record?.counts.loss).toBe(1);
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("ticker=NVDA"),
    );
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/analytics/track-record/"),
    );
  });

  it("includes direction and conviction in URL when provided", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue(MOCK_RESPONSE);
    const { result } = renderHook(
      () => useTrackRecord("NVDA", "bullish", 4),
      { wrapper: hookWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("ticker=NVDA"),
    );
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("direction=bullish"),
    );
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("conviction=4"),
    );
  });

  it("is disabled when ticker is empty", () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue(MOCK_RESPONSE);
    const { result } = renderHook(
      () => useTrackRecord(""),
      { wrapper: hookWrapper() },
    );
    expect(result.current.fetchStatus).toBe("idle");
    expect(spy).not.toHaveBeenCalled();
  });

  it("returns available:false correctly when record is null", async () => {
    const spy = vi.spyOn(client, "apiGet").mockResolvedValue({
      ticker: "XYZ",
      available: false,
      record: null,
    });
    const { result } = renderHook(
      () => useTrackRecord("XYZ"),
      { wrapper: hookWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.available).toBe(false);
    expect(result.current.data?.record).toBeNull();
    expect(spy).toHaveBeenCalledWith(expect.stringContaining("ticker=XYZ"));
  });
});
