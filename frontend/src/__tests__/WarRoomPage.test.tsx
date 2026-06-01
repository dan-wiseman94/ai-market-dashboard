import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import WarRoomPage from "@/pages/WarRoomPage";
import { renderWithProviders } from "./testUtils";

describe("WarRoomPage", () => {
  it("lists past debates with their verdict", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      {
        id: 1, created_at: "2026-06-01T12:00:00Z", subject_kind: "free", subject_label: "NVDA into earnings",
        params: { structure: "rebuttal" }, verdict: { verdict: "bull case stronger", confidence: 0.62 },
        confidence: 0.62, status: "done", error: "", thread_id: 1, messages: [],
      },
    ]);
    renderWithProviders(<WarRoomPage />);
    await waitFor(() => expect(screen.getByText(/NVDA into earnings/)).toBeInTheDocument());
    expect(screen.getByText(/bull case stronger/)).toBeInTheDocument();
  });
});
