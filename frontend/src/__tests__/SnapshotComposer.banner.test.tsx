import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SnapshotComposerPage from "@/pages/SnapshotComposerPage";

const mockMarketStatus = vi.fn();

// useSnapshotProgress subscribes to the WS channel; this test renders without
// a real WebSocketProvider — stub it to return an empty sections map.
vi.mock("@/hooks/useSnapshotProgress", () => ({
  useSnapshotProgress: () => ({ sections: new Map() }),
}));

vi.mock("@/hooks/useMarketStatus", () => ({ useMarketStatus: () => mockMarketStatus() }));
vi.mock("@/hooks/useProfiles", () => ({ useProfiles: () => ({ data: [{ id: 1, name: "P", default_includes: [] }] }) }));
vi.mock("@/hooks/useAgentPresets", () => ({ useAgentPresets: () => ({ data: [] }) }));
vi.mock("@/hooks/useWatchlists", () => ({
  useWatchlists: () => ({ data: [{ id: 1, name: "W", symbols: [{ ticker: "SPY" }] }] }),
}));
vi.mock("@/hooks/useCreateSnapshot", () => ({ useCreateSnapshot: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock("@/hooks/useCreateConsultThread", () => ({ useCreateConsultThread: () => ({ mutateAsync: vi.fn(), isPending: false }) }));
vi.mock("react-router-dom", () => ({ useNavigate: () => vi.fn() }));
vi.mock("@/components/SnapshotSectionPicker", () => ({ default: () => <div /> }));

beforeEach(() => mockMarketStatus.mockReset());

describe("SnapshotComposer market banner", () => {
  it("shows the closed banner when a relevant market is closed", () => {
    mockMarketStatus.mockReturnValue({ data: { markets: { us_equity: { is_open: false } } } });
    render(<SnapshotComposerPage />);
    expect(screen.getByRole("status")).toHaveTextContent(/market closed/i);
  });

  it("no banner when markets are open", () => {
    mockMarketStatus.mockReturnValue({ data: { markets: { us_equity: { is_open: true } } } });
    render(<SnapshotComposerPage />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});
