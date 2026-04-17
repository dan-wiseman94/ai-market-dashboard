import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import OptionChainTable from "../components/OptionChainTable";

const PAYLOAD = {
  underlying_last: "521.30",
  expiries: {
    "2026-04-25": {
      calls: [
        { strike: "515.00", bid: "7.20", ask: "7.30", delta: "0.72", iv: "18.4" },
        { strike: "520.00", bid: "3.85", ask: "3.95", delta: "0.55", iv: "17.9" },
      ],
      puts: [
        { strike: "515.00", bid: "0.95", ask: "1.00", delta: "-0.28", iv: "19.1" },
      ],
    },
  },
};

describe("OptionChainTable", () => {
  it("renders rows for both calls and puts at the same strike", () => {
    render(<OptionChainTable payload={PAYLOAD} />);
    expect(screen.getByText("521.30")).toBeInTheDocument();
    expect(screen.getByText("515.00")).toBeInTheDocument();
    expect(screen.getByText("7.20")).toBeInTheDocument();
    expect(screen.getByText("0.95")).toBeInTheDocument();
  });
});
