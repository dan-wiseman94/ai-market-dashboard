import { afterEach, describe, expect, it } from "vitest";

import {
  fetchPrediction,
  fetchPredictionStats,
  fetchPredictions,
  predictionQueryString,
} from "@/api/predictions";
import { mockApi, type FetchMock } from "../testUtils";

let mock: FetchMock | undefined;
afterEach(() => mock?.restore());

describe("predictionQueryString", () => {
  it("drops blanks and page 1", () => {
    expect(predictionQueryString({})).toBe("");
    expect(predictionQueryString({ ticker: "  ", horizon: "", page: 1 })).toBe("");
  });

  it("serializes the three filters plus a page beyond the first", () => {
    expect(predictionQueryString({ ticker: "nvda", status: "open", horizon: "7", page: 3 })).toBe(
      "?ticker=nvda&status=open&horizon=7&page=3",
    );
  });
});

describe("prediction clients", () => {
  it("hit the ledger, stats and detail paths", async () => {
    mock = mockApi({
      "GET /api/predictions/stats/": { filters: {}, totals: {}, by_ticker: [] },
      "GET /api/predictions/9/": { id: 9 },
      "GET /api/predictions/": { count: 0, next: null, previous: null, results: [] },
    });
    await fetchPredictions({ ticker: "SPY" });
    // The stats rollup is cohort-wide: `page` must not leak into its query.
    await fetchPredictionStats({ ticker: "SPY", page: 4 });
    await fetchPrediction(9);
    expect((mock.calls ?? []).map((c) => c.url)).toEqual([
      "/api/predictions/?ticker=SPY",
      "/api/predictions/stats/?ticker=SPY",
      "/api/predictions/9/",
    ]);
  });
});
