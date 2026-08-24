import { screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { mockApi, renderWithProviders } from "./testUtils";
import SnapshotsPage from "../pages/SnapshotsPage";

describe("SnapshotsPage", () => {
  it("renders captured snapshots in the table", async () => {
    mockApi({ "GET /api/snapshots/": { results: [
      { id: 1, captured_at: "2026-05-28T13:30:00Z", profile_id: 1, profile_name: "P",
        objective: "Scalp", status: "ready", source: "manual", primary_ticker: "NVDA",
        section_kinds: ["quotes"], section_statuses: { quotes: "done" }, has_image: false,
        total_payload_tokens: 10 } ] } });
    renderWithProviders(<SnapshotsPage />, { initialEntries: ["/snapshots"] });
    expect(await screen.findByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText(/Scalp/)).toBeInTheDocument();
  });
});
