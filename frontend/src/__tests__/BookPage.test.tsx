import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import BookPage from "@/pages/BookPage";
import { renderWithProviders } from "./testUtils";

const MINIMAL_BOOK = {
  id: 1, created_at: "x", as_of_date: "2026-06-01",
  exposures: [], concentration: {}, clusters: [],
  regime_fit: { alignment: "aligned", note: "" },
  near_invalidation: [], narrative: "",
};

describe("BookPage", () => {
  it("renders concentration, clusters, regime fit", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) => {
      const snap = {
        id: 1, created_at: "x", as_of_date: "2026-06-01",
        exposures: [{ ticker: "NVDA", net_signed: 7, abs_exposure: 7, dollar: null, sources: ["thesis"] }],
        concentration: { hhi: 0.42, top_n_share: 0.7, net_long: 11, net_short: -2 },
        clusters: [{ members: ["NVDA", "AMD"], avg_corr: 0.9 }],
        regime_fit: { alignment: "misaligned", note: "net-long into risk-off" },
        near_invalidation: [], narrative: "Concentrated book.",
      };
      return path.endsWith("/current/") ? snap : [snap];
    });
    renderWithProviders(<BookPage />);
    await waitFor(() => expect(screen.getAllByText(/NVDA/).length).toBeGreaterThan(0));
    expect(screen.getByText(/misaligned/i)).toBeInTheDocument();
    // cluster members are shown inline (the whole point of the cluster view)
    expect(screen.getByText(/NVDA, AMD/)).toBeInTheDocument();
  });

  it("renders the VaR / factor-beta lens when available", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) => {
      const snap = {
        id: 1, created_at: "x", as_of_date: "2026-06-01",
        exposures: [{ ticker: "NVDA", net_signed: 3, abs_exposure: 3, dollar: 10000, sources: ["position"] }],
        concentration: { hhi: 0.5, top_n_share: 1, net_long: 3, net_short: 0 },
        clusters: [], regime_fit: { alignment: "aligned", note: "" },
        near_invalidation: [], narrative: "",
        var_beta: {
          available: true,
          method: "parametric_gaussian_1d_95",
          window: 252,
          positions: [{ ticker: "NVDA", dollar: 10000, daily_vol_pct: 2.5, var_usd: 411.25, beta: 1.4 }],
          portfolio: {
            gross_dollar: 10000, net_dollar: 10000,
            undiversified_var_usd: 411.25, diversified_var_usd: 411.25,
            diversification_benefit_usd: 0, beta_adjusted_net_exposure_usd: 14000, n_positions: 1,
          },
          skipped: 0, note: "",
        },
      };
      return path.endsWith("/current/") ? snap : [snap];
    });
    renderWithProviders(<BookPage />);
    await waitFor(() =>
      expect(screen.getByText(/Value-at-Risk/i)).toBeInTheDocument(),
    );
    const summary = screen.getByTestId("book-var-summary");
    expect(summary.textContent).toMatch(/411/); // diversified VaR dollars
    // per-position beta is surfaced
    expect(screen.getByText(/β\s*1\.4/)).toBeInTheDocument();
  });

  it("empty state when no book", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) =>
      path.endsWith("/current/") ? null : [],
    );
    renderWithProviders(<BookPage />);
    await waitFor(() => expect(screen.getByText(/no book snapshot/i)).toBeInTheDocument());
  });

  it("recompute button posts to /api/book/recompute/", async () => {
    vi.spyOn(client, "apiGet").mockImplementation(async (path: string) =>
      path.endsWith("/current/") ? MINIMAL_BOOK : [MINIMAL_BOOK],
    );
    const post = vi.spyOn(client, "apiPost").mockResolvedValue(MINIMAL_BOOK as never);
    renderWithProviders(<BookPage />);
    const btn = await screen.findByRole("button", { name: /recompute/i });
    fireEvent.click(btn);
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/book/recompute/"));
  });
});
