import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import BookNarrativePanel from "@/components/book/BookNarrativePanel";
import { renderWithProviders } from "../testUtils";

describe("BookNarrativePanel", () => {
  it("renders the paragraph when one was written", () => {
    renderWithProviders(<BookNarrativePanel narrative="Concentrated in semis." />);
    expect(screen.getByText("Concentrated in semis.")).toBeInTheDocument();
  });

  it("explains the absence and points at Settings when the narrative is off", () => {
    renderWithProviders(<BookNarrativePanel narrative="" />);
    expect(screen.getByText(/No written narrative/i)).toBeInTheDocument();
    expect(screen.getByText(/computed without the AI/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /settings/i })).toHaveAttribute("href", "/settings");
  });
});
