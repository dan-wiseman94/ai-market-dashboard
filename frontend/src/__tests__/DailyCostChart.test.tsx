import { render, screen } from "@testing-library/react";
import DailyCostChart from "@/components/costs/DailyCostChart";

test("renders a chart container with supplied data points", () => {
  const data = [
    { date: "2026-04-16", cost_usd: "0.10", runs: 1 },
    { date: "2026-04-17", cost_usd: "0.20", runs: 2 },
  ];
  render(<DailyCostChart data={data} />);
  expect(screen.getByTestId("daily-cost-chart")).toBeInTheDocument();
});

test("empty data renders a placeholder", () => {
  render(<DailyCostChart data={[]} />);
  expect(screen.getByText(/no data/i)).toBeInTheDocument();
});
