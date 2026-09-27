import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BookTile } from "@/components/BookTile";
import { renderWithProviders } from "./testUtils";

describe("BookTile", () => {
  it("empty default", () => {
    renderWithProviders(<BookTile book={{ hhi: null, alignment: null, as_of: null }} />);
    expect(screen.getByText(/no snapshot/i)).toBeInTheDocument();
  });
});
