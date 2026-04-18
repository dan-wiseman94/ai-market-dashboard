import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi, test, expect, beforeEach } from "vitest";
import CostsPage from "@/pages/CostsPage";

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url: string | Request | URL) => {
    const u = String(url);
    if (u.includes("/api/costs/summary")) {
      return new Response(JSON.stringify({
        total: "0.50",
        by_provider: [{ provider: "claude", cost_usd: "0.50", runs: 5, input_tokens: 100, output_tokens: 10, cached_tokens: 0 }],
        by_model: [],
        by_thread: [],
        daily: [{ date: "2026-04-18", cost_usd: "0.50", runs: 5 }],
      }));
    }
    if (u.includes("/api/costs/caps")) {
      return new Response(JSON.stringify([
        { provider: "claude", daily: { cap: "10.00", spent: "0.50", pct: 0.05 }, monthly: null },
      ]));
    }
    return new Response("{}");
  });
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  );
}

test("CostsPage renders cap bars, chart, tables, and CSV export link", async () => {
  render(wrap(<CostsPage />));
  expect(await screen.findByText(/\$0\.50 \/ \$10\.00/)).toBeInTheDocument();
  expect(await screen.findByTestId("daily-cost-chart")).toBeInTheDocument();
  expect(await screen.findByText(/By provider/i)).toBeInTheDocument();
  expect(await screen.findByRole("link", { name: /export csv/i })).toBeInTheDocument();
});
