import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import StopButton from "@/components/StopButton";

describe("StopButton", () => {
  it("renders with aria-label Stop generation", () => {
    render(<StopButton onStop={() => {}} />);
    expect(screen.getByRole("button", { name: "Stop generation" })).toBeInTheDocument();
  });

  it("button text contains Stop", () => {
    render(<StopButton onStop={() => {}} />);
    expect(screen.getByRole("button")).toHaveTextContent("Stop");
  });

  it("click calls onStop callback once", async () => {
    const user = userEvent.setup();
    const onStop = vi.fn();
    render(<StopButton onStop={onStop} />);
    await user.click(screen.getByRole("button", { name: "Stop generation" }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });
});
