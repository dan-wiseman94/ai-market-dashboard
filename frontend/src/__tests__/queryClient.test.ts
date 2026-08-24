import { describe, expect, it } from "vitest";
import { queryClient } from "../hooks/queryClient";

describe("queryClient", () => {
  it("pins staleTime to the configured policy value", () => {
    expect(queryClient.getDefaultOptions().queries?.staleTime).toBe(1000);
  });

  it("retry policy: 4xx never retries, 5xx retries twice then stops", () => {
    const retry = queryClient.getDefaultOptions().queries?.retry as (
      failureCount: number,
      err: unknown,
    ) => boolean;
    expect(retry(0, { status: 404 })).toBe(false);
    expect(retry(0, { status: 500 })).toBe(true);
    expect(retry(1, { status: 500 })).toBe(true);
    expect(retry(2, { status: 500 })).toBe(false);
  });
});
