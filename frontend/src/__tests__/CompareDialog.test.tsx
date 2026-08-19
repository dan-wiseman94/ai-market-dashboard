import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import CompareDialog from "@/components/CompareDialog";

vi.mock("@/hooks/useAiModels", () => ({
  useAiModels: () => ({
    data: {
      models: [
        {
          id: "claude-sonnet-4-6",
          name: "Claude Sonnet 4.6",
          provider: "claude",
          input_per_mtok: 3,
          output_per_mtok: 15,
          cached_per_mtok: 0.3,
          context_window: 200000,
          supports_vision: true,
        },
        {
          id: "gpt-5-mini",
          name: "GPT-5 mini",
          provider: "openai",
          input_per_mtok: 0.5,
          output_per_mtok: 2,
          cached_per_mtok: 0.05,
          context_window: 200000,
          supports_vision: true,
        },
      ],
    },
  }),
}));

describe("CompareDialog", () => {
  it("renders dialog with placeholder text in textarea", () => {
    render(<CompareDialog onCancel={() => {}} onSubmit={() => {}} />);
    expect(
      screen.getByPlaceholderText("Your question to every branch…"),
    ).toBeInTheDocument();
  });

  it("typing in textarea updates the input value", async () => {
    const user = userEvent.setup();
    render(<CompareDialog onCancel={() => {}} onSubmit={() => {}} />);
    const textarea = screen.getByPlaceholderText("Your question to every branch…");
    await user.type(textarea, "hello");
    expect(textarea).toHaveValue("hello");
  });

  it("clicking Cancel calls onCancel", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<CompareDialog onCancel={onCancel} onSubmit={() => {}} />);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("clicking the outer overlay calls onCancel but inner card click does not", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    const { container } = render(
      <CompareDialog onCancel={onCancel} onSubmit={() => {}} />,
    );
    // The outer fixed div is the first child of the container
    const overlay = container.firstChild as HTMLElement;
    // Click directly on the overlay element (not propagated from inner)
    fireEvent.click(overlay);
    expect(onCancel).toHaveBeenCalledTimes(1);

    onCancel.mockClear();
    const innerCard = overlay.querySelector(".ledger-surface") as HTMLElement;
    await user.click(innerCard);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("clicking + add branch adds a third branch label", async () => {
    const user = userEvent.setup();
    render(<CompareDialog onCancel={() => {}} onSubmit={() => {}} />);
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.getByText("02")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /add branch/i }));
    expect(screen.getByText("03")).toBeInTheDocument();
  });

  it("remove button visible with 2 branches, hidden when only 1 branch", async () => {
    const user = userEvent.setup();
    render(<CompareDialog onCancel={() => {}} onSubmit={() => {}} />);
    const removeButtons = screen.getAllByRole("button", { name: /remove/i });
    expect(removeButtons.length).toBe(2);
    await user.click(removeButtons[0]);
    expect(screen.queryByRole("button", { name: /remove/i })).toBeNull();
  });

  it("clicking remove on branch 0 leaves branch 1 remaining", async () => {
    const user = userEvent.setup();
    render(<CompareDialog onCancel={() => {}} onSubmit={() => {}} />);
    const removeButtons = screen.getAllByRole("button", { name: /remove/i });
    await user.click(removeButtons[0]);
    // Now only 1 branch remains, re-indexed as "01"
    expect(screen.getByText("01")).toBeInTheDocument();
    expect(screen.queryByText("02")).toBeNull();
  });

  it("Dispatch button does NOT call onSubmit when text is empty", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<CompareDialog onCancel={() => {}} onSubmit={onSubmit} />);
    const dispatch = screen.getByRole("button", { name: /dispatch/i });
    await user.click(dispatch);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("Dispatch button calls onSubmit with trimmed text and branches when text present", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<CompareDialog onCancel={() => {}} onSubmit={onSubmit} />);
    await user.type(
      screen.getByPlaceholderText("Your question to every branch…"),
      "  What now?  ",
    );
    const dispatch = screen.getByRole("button", { name: /dispatch/i });
    await user.click(dispatch);
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const [text, branches] = onSubmit.mock.calls[0];
    expect(text).toBe("What now?");
    expect(branches).toHaveLength(2);
  });
});
