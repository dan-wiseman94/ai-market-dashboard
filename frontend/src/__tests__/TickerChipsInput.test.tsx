import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import TickerChipsInput from "@/components/TickerChipsInput";

describe("TickerChipsInput", () => {
  it("renders the current value as labeled, removable chips", () => {
    render(<TickerChipsInput value={["AAPL", "TSLA"]} onChange={() => {}} />);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /remove AAPL/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /remove TSLA/i })).toBeInTheDocument();
  });

  it("commits a typed ticker on Enter, uppercased", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TickerChipsInput value={[]} onChange={onChange} />);
    await user.type(screen.getByLabelText("Add tickers"), "spy{Enter}");
    expect(onChange).toHaveBeenCalledWith(["SPY"]);
  });

  it("commits a typed ticker on comma", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TickerChipsInput value={["AAPL"]} onChange={onChange} />);
    await user.type(screen.getByLabelText("Add tickers"), "nvda,");
    expect(onChange).toHaveBeenCalledWith(["AAPL", "NVDA"]);
  });

  it("does not add a duplicate that is already present", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TickerChipsInput value={["AAPL"]} onChange={onChange} />);
    await user.type(screen.getByLabelText("Add tickers"), "aapl{Enter}");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("ignores blank input", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TickerChipsInput value={[]} onChange={onChange} />);
    await user.type(screen.getByLabelText("Add tickers"), "   {Enter}");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("ignores input with invalid ticker characters", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TickerChipsInput value={[]} onChange={onChange} />);
    await user.type(screen.getByLabelText("Add tickers"), "$$${Enter}");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("removes a chip when its × button is clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TickerChipsInput value={["AAPL", "TSLA"]} onChange={onChange} />);
    await user.click(screen.getByRole("button", { name: /remove TSLA/i }));
    expect(onChange).toHaveBeenCalledWith(["AAPL"]);
  });

  it("removes the last chip on Backspace when the input is empty", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TickerChipsInput value={["AAPL", "TSLA"]} onChange={onChange} />);
    const input = screen.getByLabelText("Add tickers");
    input.focus();
    await user.keyboard("{Backspace}");
    expect(onChange).toHaveBeenCalledWith(["AAPL"]);
  });
});
