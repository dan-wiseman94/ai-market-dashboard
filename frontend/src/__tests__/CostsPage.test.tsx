import { screen } from "@testing-library/react";
import { test, expect, beforeEach } from "vitest";
import CostsPage from "@/pages/CostsPage";
import { mockApi, renderWithProviders } from "./testUtils";

beforeEach(() => {
  mockApi({
    "GET /api/costs/summary": {
      total: "0.50",
      by_provider: [{ provider: "claude", cost_usd: "0.50", runs: 5, input_tokens: 100, output_tokens: 10, cached_tokens: 0 }],
      by_model: [],
      by_thread: [],
      daily: [{ date: "2026-04-18", cost_usd: "0.50", runs: 5 }],
    },
    "GET /api/costs/caps": [
      { provider: "claude", daily: { cap: "10.00", spent: "0.50", pct: 0.05 }, monthly: null },
    ],
    "GET /api/costs/today/": {},
  });
});

test("CostsPage renders cap bars, chart, tables, and CSV export link", async () => {
  renderWithProviders(<CostsPage />);
  expect(await screen.findByText(/\$0\.50 \/ \$10\.00/)).toBeInTheDocument();
  expect(await screen.findByTestId("daily-cost-chart")).toBeInTheDocument();
  expect(await screen.findByText(/By provider/i)).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: /export csv/i })).toBeInTheDocument();
});
