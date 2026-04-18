import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import BreakdownTables from "@/components/costs/BreakdownTables";
import type { CostsSummary } from "@/api/costs";

const s: CostsSummary = {
  total: "0.30",
  by_provider: [{ provider: "claude", cost_usd: "0.20", runs: 5, input_tokens: 100, output_tokens: 10, cached_tokens: 0 }],
  by_model: [{ provider: "claude", model: "claude-sonnet-4-6", cost_usd: "0.20", runs: 5, input_tokens: 100, output_tokens: 10, cached_tokens: 0 }],
  by_thread: [{ thread_id: 1, title: "alpha", cost_usd: "0.15", runs: 3 }],
  daily: [],
};

test("renders provider, model, and top-threads tables", () => {
  render(<MemoryRouter><BreakdownTables summary={s} /></MemoryRouter>);
  expect(screen.getByText(/By provider/i)).toBeInTheDocument();
  expect(screen.getByText(/By model/i)).toBeInTheDocument();
  expect(screen.getByText(/Top 10 threads/i)).toBeInTheDocument();
  expect(screen.getByText("claude-sonnet-4-6")).toBeInTheDocument();
  expect(screen.getByText("alpha")).toBeInTheDocument();
});

test("top-thread row links to /threads/:id", () => {
  render(<MemoryRouter><BreakdownTables summary={s} /></MemoryRouter>);
  const link = screen.getByRole("link", { name: /alpha/i });
  expect(link).toHaveAttribute("href", "/threads/1");
});
