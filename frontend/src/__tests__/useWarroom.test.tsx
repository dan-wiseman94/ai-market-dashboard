import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import { useWarRoomRuns } from "@/hooks/useWarroom";
import { hookWrapper } from "./testUtils";

describe("useWarRoomRuns", () => {
  it("lists runs", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      { id: 1, created_at: "x", subject_kind: "free", subject_label: "q", params: {}, verdict: { verdict: "balanced" }, confidence: 0.5, status: "done", error: "", thread_id: 1, messages: [] },
    ]);
    const { result } = renderHook(() => useWarRoomRuns(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.data?.length).toBe(1));
  });
});
