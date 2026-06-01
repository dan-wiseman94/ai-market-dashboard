import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import DeskPage from "@/pages/DeskPage";
import { renderWithProviders } from "./testUtils";

describe("DeskPage", () => {
  it("renders findings + suggested action", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      { id: 1, created_at: "2026-06-01T12:00:00Z", anomaly_type: "price_move", ticker: "NVDA", severity: 9, evidence: {}, finding: "NVDA gapped on capex.", suggested_actions: [{ type: "convene_warroom", label: "Convene War Room on NVDA" }], status: "new", warroom_run_id: null },
    ]);
    renderWithProviders(<DeskPage />);
    await waitFor(() => expect(screen.getByText(/NVDA gapped on capex/)).toBeInTheDocument());
    expect(screen.getByText(/Convene War Room on NVDA/)).toBeInTheDocument();
  });
});
