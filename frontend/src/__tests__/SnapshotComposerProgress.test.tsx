/**
 * Integration test: SnapshotComposerPage progress checklist wiring.
 *
 * Verifies that, while a capture is in-flight (submitting=true):
 *  - The page subscribes to the snapshot.<id> WS channel
 *  - snapshot.section events are rendered as a per-section checklist
 *  - The HTTP poll is kept (waitForSnapshotReady is still called)
 */
import { screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import {
  renderWithProviders,
  installFakeWebSocket,
  type FakeWebSocketController,
  newQueryClient,
} from "./testUtils";
import SnapshotComposerPage from "@/pages/SnapshotComposerPage";

const mockCreateSnap = vi.fn();
const mockCreateThread = vi.fn();
const mockWaitForReady = vi.fn();

vi.mock("@/api/snapshots", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/snapshots")>()),
  waitForSnapshotReady: (...args: unknown[]) => mockWaitForReady(...args),
}));

vi.mock("@/hooks/useCreateSnapshot", () => ({
  useCreateSnapshot: () => ({ mutateAsync: mockCreateSnap, isPending: false }),
}));

vi.mock("@/hooks/useCreateConsultThread", () => ({
  useCreateConsultThread: () => ({ mutateAsync: mockCreateThread, isPending: false }),
}));

vi.mock("@/hooks/useProfiles", () => ({
  useProfiles: () => ({
    data: [{ id: 1, name: "Day Trader", default_includes: ["quotes", "ohlc"] }],
  }),
}));

vi.mock("@/hooks/useWatchlists", () => ({
  useWatchlists: () => ({
    data: [{ id: 10, name: "Tech", tickers: [{ ticker: "AAPL" }] }],
  }),
}));

vi.mock("@/hooks/useAgentPresets", () => ({
  useAgentPresets: () => ({ data: [] }),
}));

// Wrap with WebSocketProvider in addition to the standard providers so
// useSnapshotProgress can subscribe to the snapshot.<id> channel.
function renderWithWs() {
  const client = newQueryClient();
  const { container } = renderWithProviders(
    <WebSocketProvider>
      <SnapshotComposerPage />
    </WebSocketProvider>,
    {
      client,
      initialEntries: ["/compose"],
      routePath: "/compose",
    },
  );
  return { container, client };
}

let fake: FakeWebSocketController;

beforeEach(() => {
  fake = installFakeWebSocket();
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(() => {
  fake.restore();
  localStorage.clear();
});

describe("SnapshotComposerPage – capture progress (WS integration)", () => {
  it("shows per-section progress entries after WS events arrive during capture", async () => {
    const user = userEvent.setup();

    // createSnapshot returns immediately with "pending"; poll stays blocked so
    // we can observe the in-flight state with WS events arriving.
    mockCreateSnap.mockResolvedValue({ id: 55, status: "pending", includes: [] });
    let resolveReady!: (s: { id: number; status: string }) => void;
    mockWaitForReady.mockReturnValue(
      new Promise((resolve) => {
        resolveReady = resolve;
      }),
    );
    mockCreateThread.mockResolvedValue({ id: 99, title: "t" });

    renderWithWs();

    await waitFor(() => {
      const [sel] = screen.getAllByRole("combobox");
      expect((sel as HTMLSelectElement).value).toBe("1");
    });

    await user.click(screen.getByTestId("capture-btn"));

    // The page calls createSnap, then sets capturingId=55 and starts polling.
    // The WS channel for snapshot.55 should be open.
    await waitFor(() => {
      expect(fake.find("/ws/snapshots/55/")).toBeDefined();
    });

    const sock = fake.find("/ws/snapshots/55/")!;

    act(() => {
      sock.emitMessage({ type: "snapshot.section", section: "quotes", status: "running" });
    });

    await waitFor(() => {
      expect(screen.getByTestId("capture-progress")).toBeInTheDocument();
    });
    const progress = screen.getByTestId("capture-progress");
    expect(progress).toHaveTextContent("quotes");
    expect(progress).toHaveTextContent("⏳");

    act(() => {
      sock.emitMessage({ type: "snapshot.section", section: "quotes", status: "done" });
      sock.emitMessage({ type: "snapshot.section", section: "news", status: "failed" });
    });

    await waitFor(() => {
      expect(progress).toHaveTextContent("✓");
      expect(progress).toHaveTextContent("✗");
    });
    expect(progress).toHaveTextContent("quotes");
    expect(progress).toHaveTextContent("news");

    // The HTTP poll must still be in flight (not yet resolved)
    expect(mockWaitForReady).toHaveBeenCalledWith(55);
    expect(mockCreateThread).not.toHaveBeenCalled();

    // Unblock the poll — navigation takes over
    resolveReady({ id: 55, status: "ready" });
    await waitFor(() => expect(mockCreateThread).toHaveBeenCalled());
  });
});
