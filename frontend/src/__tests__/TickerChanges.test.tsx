import { screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "./testUtils";
import { TickerChanges } from "@/pages/watchlist/TickerChanges";
import * as snapshotsApi from "@/api/snapshots";

const SNAP = {
  id: 7,
  captured_at: "2026-05-01",
  profile_id: 1,
  profile_name: "p",
  objective: "",
  status: "ready",
  source: "manual",
  primary_ticker: "NVDA",
  section_kinds: [],
  section_statuses: {},
  has_image: false,
  total_payload_tokens: 0,
};

describe("TickerChanges", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("is collapsed by default and fetches nothing until expanded", () => {
    const timelineSpy = vi.spyOn(snapshotsApi, "fetchSnapshotTimeline");
    renderWithProviders(<TickerChanges ticker="NVDA" />);
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("What changed?")).toBeInTheDocument();
    expect(timelineSpy).not.toHaveBeenCalled();
  });

  it("expands to show the latest snapshot's diff", async () => {
    vi.spyOn(snapshotsApi, "fetchSnapshotTimeline").mockResolvedValue({ results: [SNAP] } as never);
    vi.spyOn(snapshotsApi, "fetchSnapshotDiff").mockResolvedValue({
      delta: "AAPL last 150 -> 155",
      prev_id: 6,
      curr_id: 7,
    });
    renderWithProviders(<TickerChanges ticker="NVDA" />);
    fireEvent.click(screen.getByRole("button", { name: /what changed/i }));
    await waitFor(() => expect(screen.getByText(/AAPL last 150/)).toBeInTheDocument());
    expect(screen.getByText(/snapshot #7/)).toBeInTheDocument();
  });

  it("shows a friendly message when the ticker has no snapshots", async () => {
    vi.spyOn(snapshotsApi, "fetchSnapshotTimeline").mockResolvedValue({ results: [] } as never);
    renderWithProviders(<TickerChanges ticker="TSLA" />);
    fireEvent.click(screen.getByRole("button", { name: /what changed/i }));
    await waitFor(() => expect(screen.getByText(/No snapshots of TSLA yet/)).toBeInTheDocument());
  });
});
