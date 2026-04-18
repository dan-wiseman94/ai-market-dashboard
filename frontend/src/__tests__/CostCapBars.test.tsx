import { render, screen } from "@testing-library/react";
import CostCapBars from "@/components/costs/CostCapBars";
import type { CapRow } from "@/api/costs";

const rows: CapRow[] = [
  {
    provider: "claude",
    daily: { cap: "10.00", spent: "3.20", pct: 0.32 },
    monthly: { cap: "300.00", spent: "42.00", pct: 0.14 },
  },
];

test("renders daily cap bar with amount + percent", () => {
  render(<CostCapBars rows={rows} />);
  expect(screen.getByText(/claude/i)).toBeInTheDocument();
  expect(screen.getByText(/\$3\.20 \/ \$10\.00/)).toBeInTheDocument();
  expect(screen.getByText(/32%/)).toBeInTheDocument();
});

test("amber at >=80%, red at >=100%", () => {
  const hot: CapRow[] = [{
    provider: "claude",
    daily: { cap: "1.00", spent: "0.90", pct: 0.9 }, monthly: null,
  }];
  const { container, rerender } = render(<CostCapBars rows={hot} />);
  expect(container.querySelector(".bg-amber-500")).toBeInTheDocument();

  const over: CapRow[] = [{
    provider: "claude",
    daily: { cap: "1.00", spent: "1.20", pct: 1.0 }, monthly: null,
  }];
  rerender(<CostCapBars rows={over} />);
  expect(container.querySelector(".bg-rose-500")).toBeInTheDocument();
});

test("hides monthly row when cap null", () => {
  const none: CapRow[] = [{
    provider: "claude",
    daily: { cap: "10.00", spent: "1.00", pct: 0.1 }, monthly: null,
  }];
  render(<CostCapBars rows={none} />);
  expect(screen.queryByText(/monthly/i)).not.toBeInTheDocument();
});
