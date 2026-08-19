import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import BranchTabs from "@/components/BranchTabs";

describe("BranchTabs", () => {
  it("renders null when branches is empty", () => {
    const { container } = render(
      <BranchTabs branches={[]} activeId={null} onSelect={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders one button per branch", () => {
    render(
      <BranchTabs
        branches={[
          { id: 1, label: "claude/sonnet", status: "done" },
          { id: 2, label: "openai/gpt-5", status: "done" },
        ]}
        activeId={null}
        onSelect={() => {}}
      />,
    );
    expect(screen.getAllByRole("button")).toHaveLength(2);
  });

  it("clicking a branch calls onSelect with branch id", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <BranchTabs
        branches={[{ id: 7, label: "claude/haiku", status: "done" }]}
        activeId={null}
        onSelect={onSelect}
      />,
    );
    await user.click(screen.getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith(7);
  });

  it("active branch button gets text-copper-200 class", () => {
    render(
      <BranchTabs
        branches={[
          { id: 1, label: "claude/sonnet", status: "done" },
          { id: 2, label: "openai/gpt-5", status: "done" },
        ]}
        activeId={1}
        onSelect={() => {}}
      />,
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons[0].className).toContain("text-copper-200");
    expect(buttons[1].className).not.toContain("text-copper-200");
  });

  it("streaming branch without cost shows the cost-pending pulse indicator", () => {
    render(
      <BranchTabs
        branches={[{ id: 3, label: "claude/sonnet", status: "streaming" }]}
        activeId={3}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("branch-cost-pending-3")).toBeInTheDocument();
  });

  it("done branch with cost shows the formatted cost badge", () => {
    render(
      <BranchTabs
        branches={[{ id: 1, label: "claude/sonnet", status: "done", cost: 0.0123 }]}
        activeId={1}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("branch-cost-1")).toHaveTextContent("$0.0123");
  });

  it("failed branch shows the X marker", () => {
    render(
      <BranchTabs
        branches={[{ id: 5, label: "openai/gpt-5", status: "failed" }]}
        activeId={null}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText("✗")).toBeInTheDocument();
  });
});
