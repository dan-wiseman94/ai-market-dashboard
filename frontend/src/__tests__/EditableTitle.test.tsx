import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EditableTitle from "@/pages/thread-detail/EditableTitle";

describe("EditableTitle", () => {
  it("shows a placeholder when the title is empty", () => {
    render(<EditableTitle title="" onSave={vi.fn()} />);
    expect(screen.getByText(/Untitled consultation/)).toBeInTheDocument();
  });

  it("enters edit mode and saves the trimmed new title", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<EditableTitle title="Old" onSave={onSave} />);
    await user.click(screen.getByTestId("rename-thread-btn"));
    const input = screen.getByTestId("rename-thread-input");
    await user.clear(input);
    await user.type(input, "  New name  ");
    await user.click(screen.getByTestId("rename-thread-save"));
    expect(onSave).toHaveBeenCalledWith("New name");
  });

  it("cancels without saving on Escape", async () => {
    const onSave = vi.fn();
    const user = userEvent.setup();
    render(<EditableTitle title="Old" onSave={onSave} />);
    await user.click(screen.getByTestId("rename-thread-btn"));
    await user.type(screen.getByTestId("rename-thread-input"), "x{Escape}");
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText("Old")).toBeInTheDocument();
  });
});
