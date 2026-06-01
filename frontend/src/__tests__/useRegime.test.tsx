import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { useCurrentRegime } from "@/hooks/useRegime";
import { hookWrapper } from "./testUtils";

describe("useCurrentRegime", () => {
  it("returns the current regime", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue({
      id: 1, created_at: "2026-06-01T12:00:00Z", composite: "Risk-Off",
      axes: { volatility: "Elevated" }, drivers: ["VIX 24 — Elevated"],
      narrative: "", changed_axes: [],
    });
    const { result } = renderHook(() => useCurrentRegime(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.data?.composite).toBe("Risk-Off"));
  });
});
