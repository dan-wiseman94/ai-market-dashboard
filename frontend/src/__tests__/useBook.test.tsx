import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { useCurrentBook } from "@/hooks/useBook";
import { hookWrapper } from "./testUtils";

describe("useCurrentBook", () => {
  it("returns the current book snapshot", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 1, created_at: "x", as_of_date: "2026-06-01",
      exposures: [], concentration: { hhi: 0.4 }, clusters: [],
      regime_fit: { alignment: "misaligned" }, near_invalidation: [], narrative: "",
    });
    const { result } = renderHook(() => useCurrentBook(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.data?.concentration.hhi).toBe(0.4));
  });
});
