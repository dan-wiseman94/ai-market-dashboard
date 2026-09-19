import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import SnapshotSectionPicker from "@/components/SnapshotSectionPicker";

// Mirrors SECTION_LABELS (frontend/src/lib/snapshotSections.ts), which mirrors
// backend/apps/snapshots/serializer.py::_title verbatim.
const LABELS = [
  "Quotes",
  "OHLC",
  "Option chain",
  "Positions",
  "Market breadth",
  "News",
  "Upcoming events",
  "Macro",
  "Company fundamentals",
  "SEC filings",
  "Treasury",
  "Overnight board",
  "Chart image",
  "Notes",
  "Fed communication",
  "Flow proxy (volume-based)",
];

describe("SnapshotSectionPicker", () => {
  it("renders 16 labeled checkboxes", () => {
    render(<SnapshotSectionPicker value={[]} onChange={() => {}} />);
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(16);
    for (const label of LABELS) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  it("offers overnight, fundamentals, fed, and flowlite", () => {
    render(<SnapshotSectionPicker value={[]} onChange={() => {}} />);
    expect(screen.getByLabelText("Overnight board")).toBeInTheDocument();
    expect(screen.getByLabelText("Company fundamentals")).toBeInTheDocument();
    expect(screen.getByLabelText("Fed communication")).toBeInTheDocument();
    expect(screen.getByLabelText("Flow proxy (volume-based)")).toBeInTheDocument();
  });

  it("checkboxes reflect value prop checked states", () => {
    render(
      <SnapshotSectionPicker value={["quotes", "ohlc"]} onChange={() => {}} />,
    );
    expect(screen.getByLabelText("Quotes")).toBeChecked();
    expect(screen.getByLabelText("OHLC")).toBeChecked();
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
