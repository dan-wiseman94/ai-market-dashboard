import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { BriefingSummaryTile } from "@/components/dashboard/BriefingSummaryTile";
import { renderWithProviders } from "../testUtils";

const briefingFixture = {
  id: 99,
  status: "ready",
  created_at: "2026-05-30T08:00:00Z",
  scheduled_date: "2026-05-30",
};

describe("BriefingSummaryTile", () => {
  it("shows status badge and scheduled_date when briefing is present", () => {
    renderWithProviders(<BriefingSummaryTile briefing={briefingFixture} />);
    expect(screen.getByText("ready")).toBeInTheDocument();
    expect(screen.getByText("2026-05-30")).toBeInTheDocument();
  });

  it("shows EmptyState when briefing is null", () => {
    renderWithProviders(<BriefingSummaryTile briefing={null} />);
    expect(screen.getByText(/No briefing yet/i)).toBeInTheDocument();
  });

  it("links to /briefing", () => {
    renderWithProviders(<BriefingSummaryTile briefing={briefingFixture} />);
    const links = screen.getAllByRole("link", { name: /briefing|open|read/i });
    const briefingLink = links.find((l) => l.getAttribute("href") === "/briefing");
    expect(briefingLink).toBeTruthy();
  });

  it("shows 'Open →' header link even when briefing is null", () => {
    renderWithProviders(<BriefingSummaryTile briefing={null} />);
    const link = screen.getByRole("link", { name: /Open/i });
    expect(link).toHaveAttribute("href", "/briefing");
  });
});
