import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import SnapshotSectionPicker from "@/components/SnapshotSectionPicker";

const LABELS = [
  "Quotes",
  "OHLC bars",
  "Positions",
  "Market context",
  "My notes",
  "Option chain",
  "News",
  "Upcoming events",
  "Charts (server-render)",
];

describe("SnapshotSectionPicker", () => {
  it("renders 9 labeled checkboxes", () => {
    render(<SnapshotSectionPicker value={[]} onChange={() => {}} />);
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(9);
    for (const label of LABELS) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  it("checkboxes reflect value prop checked states", () => {
    render(
      <SnapshotSectionPicker value={["quotes", "ohlc"]} onChange={() => {}} />,
    );
    expect(screen.getByLabelText("Quotes")).toBeChecked();
    expect(screen.getByLabelText("OHLC bars")).toBeChecked();
    expect(screen.getByLabelText("Positions")).not.toBeChecked();
  });

  it("clicking unchecked checkbox calls onChange with key added", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<SnapshotSectionPicker value={["quotes"]} onChange={onChange} />);
    await user.click(screen.getByLabelText("News"));
    expect(onChange).toHaveBeenCalledWith(["quotes", "news"]);
  });

  it("clicking checked checkbox calls onChange with key removed", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <SnapshotSectionPicker value={["quotes", "news"]} onChange={onChange} />,
    );
    await user.click(screen.getByLabelText("Quotes"));
    expect(onChange).toHaveBeenCalledWith(["news"]);
  });

  it("each checkbox has an associated label accessible via getByLabelText", () => {
    render(<SnapshotSectionPicker value={[]} onChange={() => {}} />);
    for (const label of LABELS) {
      const checkbox = screen.getByLabelText(label);
      expect(checkbox).toHaveAttribute("type", "checkbox");
    }
  });
});
