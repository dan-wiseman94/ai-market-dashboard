import { render, screen } from "@testing-library/react";
import CompareTotalsStrip from "@/components/CompareTotalsStrip";
import type { BranchState } from "@/hooks/useBranchState";

test("sums cost and reports slowest duration across branches", () => {
  const state: Record<number, BranchState> = {
    1: { status: "done", cost: 0.0100, durationMs: 1200 },
    2: { status: "done", cost: 0.0148, durationMs: 1800 },
  };
  render(<CompareTotalsStrip state={state} />);
  expect(screen.getByText(/\$0\.0248/)).toBeInTheDocument();
  expect(screen.getByText(/2 branches/)).toBeInTheDocument();
  expect(screen.getByText(/1\.8s slowest/)).toBeInTheDocument();
});

test("renders nothing when no branches have cost yet", () => {
  const { container } = render(<CompareTotalsStrip state={{}} />);
  expect(container).toBeEmptyDOMElement();
});
