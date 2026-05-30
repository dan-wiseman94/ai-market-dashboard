import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { UpcomingEventsRow } from "@/components/dashboard/UpcomingEventsRow";
import { renderWithProviders } from "../testUtils";
import type { DashboardEvents } from "@/hooks/useDashboard";

const eventsFixture: DashboardEvents = {
  earnings: [
    {
      kind: "earnings",
      ticker: "AAPL",
      title: "AAPL earnings (BMO)",
      event_time: "2026-06-01T13:00:00+00:00",
      days_until: 2,
      when_hint: "bmo",
      impact: "high",
      detail: {},
    },
    {
      kind: "earnings",
      ticker: "NVDA",
      title: "NVDA earnings (AMC)",
      event_time: "2026-06-03T21:00:00+00:00",
      days_until: 4,
      when_hint: "amc",
      impact: "high",
      detail: {},
    },
  ],
  macro: [
    {
      kind: "fomc",
      ticker: "",
      title: "FOMC decision",
      event_time: "2026-06-04T18:00:00+00:00",
      days_until: 5,
      when_hint: "",
      impact: "high",
      detail: {},
    },
  ],
};

describe("UpcomingEventsRow", () => {
  it("shows earnings chips with ticker and days_until", () => {
    renderWithProviders(<UpcomingEventsRow events={eventsFixture} />);
    expect(screen.getByText(/AAPL earnings/i)).toBeInTheDocument();
    expect(screen.getByText(/NVDA earnings/i)).toBeInTheDocument();
    // days_until labels
    expect(screen.getByText("2d")).toBeInTheDocument();
    expect(screen.getByText("4d")).toBeInTheDocument();
  });

  it("shows macro event title", () => {
    renderWithProviders(<UpcomingEventsRow events={eventsFixture} />);
    expect(screen.getByText("FOMC decision")).toBeInTheDocument();
  });

  it("shows EmptyState when both arrays are empty", () => {
    renderWithProviders(
      <UpcomingEventsRow events={{ earnings: [], macro: [] }} />,
    );
    expect(screen.getByText(/No events in the next 7 days/i)).toBeInTheDocument();
  });

  it("all chips link to /events", () => {
    renderWithProviders(<UpcomingEventsRow events={eventsFixture} />);
    const links = screen.getAllByRole("link");
    // All event chips + the header Calendar link → all href /events
    const eventLinks = links.filter(
      (l) => l.getAttribute("href") === "/events",
    );
    expect(eventLinks.length).toBeGreaterThanOrEqual(3); // 2 earnings + 1 macro + header
  });
});
