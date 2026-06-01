import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BookTile } from "@/components/BookTile";
import { renderWithProviders } from "./testUtils";

describe("BookTile", () => {
  it("renders alignment + hhi", () => {
    renderWithProviders(<BookTile book={{ hhi: 0.42, alignment: "misaligned", as_of: "2026-06-01" }} />);
    expect(screen.getByText(/misaligned/i)).toBeInTheDocument();
  });
  it("empty default", () => {
    renderWithProviders(<BookTile book={{ hhi: null, alignment: null, as_of: null }} />);
    expect(screen.getByText(/no snapshot/i)).toBeInTheDocument();
  });
});
