import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useMarketContext } from "@/hooks/useMarketContext";
import { hookWrapper, mockApi } from "../testUtils";

const marketContextFixture = {
  spx_last: 520.5,
  qqq_last: 440.2,
  vix_last: 14.3,
  sectors: { XLK: 1.2, XLF: -0.5 },
  breadth: { advance_decline: 0.7 },
};

describe("useMarketContext", () => {
  it("returns market context on success and starts in loading state", async () => {
    mockApi({ "GET /api/market/context/": marketContextFixture });
    const { result } = renderHook(() => useMarketContext(), { wrapper: hookWrapper() });
    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.spx_last).toBe(520.5);
    expect(result.current.data?.vix_last).toBe(14.3);
  });
});
