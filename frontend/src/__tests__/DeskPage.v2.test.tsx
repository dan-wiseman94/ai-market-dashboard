import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import DeskPage from "@/pages/DeskPage";
import { renderWithProviders } from "./testUtils";

describe("DeskPage v2", () => {
  it("shows a revise-coverage action + an investigation link", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      {
        id: 1, created_at: "2026-06-01T12:00:00Z", anomaly_type: "coverage_stale", ticker: "NVDA",
        severity: 8, evidence: {}, finding: "stale",
        suggested_actions: [{ type: "revise_coverage", label: "Revise coverage on NVDA" }],
        status: "new", warroom_run_id: null, investigation_thread_id: 42,
      },
    ]);
    renderWithProviders(<DeskPage />);
    await waitFor(() => expect(screen.getByText(/Revise coverage on NVDA/)).toBeInTheDocument());
    expect(screen.getByText(/investigation/i)).toBeInTheDocument();
  });
});
