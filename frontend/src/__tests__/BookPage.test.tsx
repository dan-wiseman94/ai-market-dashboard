import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import BookPage from "@/pages/BookPage";
import { renderWithProviders } from "./testUtils";

describe("BookPage", () => {
  it("renders concentration, clusters, regime fit", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) => {
      const snap = {
        id: 1, created_at: "x", as_of_date: "2026-06-01",
        exposures: [{ ticker: "NVDA", net_signed: 7, abs_exposure: 7, dollar: null, sources: ["thesis"] }],
        concentration: { hhi: 0.42, top_n_share: 0.7, net_long: 11, net_short: -2 },
        clusters: [{ members: ["NVDA", "AMD"], avg_corr: 0.9 }],
        regime_fit: { alignment: "misaligned", note: "net-long into risk-off" },
        near_invalidation: [], narrative: "Concentrated book.", coverage: {},
      };
      return path.endsWith("/current/") ? snap : [snap];
    });
    renderWithProviders(<BookPage />);
    await waitFor(() => expect(screen.getAllByText(/NVDA/).length).toBeGreaterThan(0));
    expect(screen.getByText(/misaligned/i)).toBeInTheDocument();
    // cluster members are shown inline (the whole point of the cluster view)
    expect(screen.getByText(/NVDA, AMD/)).toBeInTheDocument();
  });

  it("empty state when no book", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) =>
      path.endsWith("/current/") ? null : [],
    );
    renderWithProviders(<BookPage />);
    await waitFor(() => expect(screen.getByText(/no book snapshot/i)).toBeInTheDocument());
  });
});
