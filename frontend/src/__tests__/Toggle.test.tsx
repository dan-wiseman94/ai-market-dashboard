import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Toggle from "@/components/ui/Toggle";

describe("Toggle", () => {
  it("renders a switch reflecting checked state", () => {
    render(<Toggle checked label="Enable thing" onChange={() => {}} />);
    const sw = screen.getByRole("switch", { name: "Enable thing" });
    expect(sw).toHaveAttribute("aria-checked", "true");
  });

  it("calls onChange with the negated value on click", async () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} label="Enable thing" onChange={onChange} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("is operable by keyboard (Space)", async () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} label="Enable thing" onChange={onChange} />);
    screen.getByRole("switch").focus();
    await userEvent.keyboard(" ");
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("does not fire when disabled", async () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} label="Enable thing" disabled onChange={onChange} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).not.toHaveBeenCalled();
  });
});
