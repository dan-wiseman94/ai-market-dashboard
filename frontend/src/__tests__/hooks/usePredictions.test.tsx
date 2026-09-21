import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { usePrediction } from "@/hooks/usePredictions";
import { hookWrapper, mockApi, type FetchMock } from "../testUtils";

let mock: FetchMock | undefined;
afterEach(() => mock?.restore());

describe("usePrediction", () => {
  it("fetches one ledger row by id", async () => {
    mock = mockApi({ "GET /api/predictions/12/": { id: 12, ticker: "SPY" } });
    const { result } = renderHook(() => usePrediction(12), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.data?.ticker).toBe("SPY"));
  });

  it("stays idle without an id", () => {
    // No route is mocked: an enabled query here would throw "no handler".
    mock = mockApi({});
    const { result } = renderHook(() => usePrediction(null), { wrapper: hookWrapper() });
    expect(result.current.fetchStatus).toBe("idle");
  });
});
