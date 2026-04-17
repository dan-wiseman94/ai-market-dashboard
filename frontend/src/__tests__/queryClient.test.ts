import { describe, expect, it } from "vitest";
import { queryClient } from "../hooks/queryClient";

describe("queryClient", () => {
  it("exposes a shared QueryClient with expected defaults", () => {
    const opts = queryClient.getDefaultOptions();
    expect(opts.queries?.staleTime).toBeGreaterThanOrEqual(0);
    expect(opts.queries?.retry).toBeDefined();
  });
});
