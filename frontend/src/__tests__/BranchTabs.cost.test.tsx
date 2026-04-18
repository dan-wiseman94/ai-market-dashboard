import { render, screen } from "@testing-library/react";
import BranchTabs from "@/components/BranchTabs";

test("renders pulsing dot while branch is streaming", () => {
  render(
    <BranchTabs
      branches={[{ id: 1, label: "claude/sonnet", status: "streaming" }]}
      activeId={1}
      onSelect={() => {}}
    />,
  );
  expect(screen.getByTestId("branch-cost-pending-1")).toBeInTheDocument();
});

test("renders formatted cost badge when cost provided", () => {
  render(
    <BranchTabs
      branches={[{ id: 1, label: "claude/sonnet", status: "done", cost: 0.0123 }]}
      activeId={1}
      onSelect={() => {}}
    />,
  );
  expect(screen.getByTestId("branch-cost-1")).toHaveTextContent("$0.0123");
});
