import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DeskTile } from "@/components/DeskTile";
import { renderWithProviders } from "./testUtils";

describe("DeskTile", () => {
  it("shows unread count", () => {
    renderWithProviders(<DeskTile desk={{ unread: 3, latest: "NVDA gapped" }} />);
    expect(screen.getByText(/3/)).toBeInTheDocument();
  });
  it("empty", () => {
    renderWithProviders(<DeskTile desk={{ unread: 0, latest: null }} />);
    expect(screen.getByText(/no new/i)).toBeInTheDocument();
  });
});
