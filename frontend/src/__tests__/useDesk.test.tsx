import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { useDeskFeed } from "@/hooks/useDesk";
import { hookWrapper } from "./testUtils";

describe("useDeskFeed", () => {
  it("lists entries", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      { id: 1, created_at: "x", anomaly_type: "price_move", ticker: "NVDA", severity: 9, evidence: {}, finding: "big move", suggested_actions: [], status: "new", warroom_run_id: null },
    ]);
    const { result } = renderHook(() => useDeskFeed(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.data?.length).toBe(1));
  });
});
