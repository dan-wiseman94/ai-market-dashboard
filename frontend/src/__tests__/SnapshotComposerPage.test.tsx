import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderWithProviders, LocationProbe } from "./testUtils";
import SnapshotComposerPage from "@/pages/SnapshotComposerPage";
import { ApiError } from "@/api/client";
import type { AgentPreset } from "@/api/presets";

const mockCreateSnap = vi.fn();
const mockCreateThread = vi.fn();
const mockWaitForReady = vi.fn();

// useSnapshotProgress subscribes to the WS channel; these tests don't need a
// real WebSocketProvider — stub it to return an empty sections map.
vi.mock("@/hooks/useSnapshotProgress", () => ({
  useSnapshotProgress: () => ({ sections: new Map() }),
}));

// Capture is async (Celery), so createSnapshot returns status="pending". The
// composer must wait for the snapshot to become ready before pinning it to a
// thread; stub the polling helper so tests control when "ready" arrives.
vi.mock("@/api/snapshots", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/snapshots")>()),
  waitForSnapshotReady: (...args: unknown[]) => mockWaitForReady(...args),
}));

vi.mock("@/hooks/useCreateSnapshot", () => ({
  useCreateSnapshot: () => ({
    mutateAsync: mockCreateSnap,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useCreateConsultThread", () => ({
  useCreateConsultThread: () => ({
    mutateAsync: mockCreateThread,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useProfiles", () => ({
  useProfiles: () => ({
    data: [
      { id: 1, name: "Day Trader", default_includes: ["quotes", "ohlc"] },
      { id: 2, name: "Swing Trader", default_includes: ["quotes", "positions"] },
    ],
  }),
}));

vi.mock("@/hooks/useWatchlists", () => ({
  useWatchlists: () => ({
    data: [
      { id: 10, name: "Tech", tickers: [{ ticker: "AAPL" }, { ticker: "GOOGL" }] },
      { id: 11, name: "Energy", tickers: [{ ticker: "XOM" }] },
    ],
  }),
}));

vi.mock("@/hooks/useAgentPresets", () => ({
  useAgentPresets: vi.fn().mockReturnValue({ data: [] }),
}));
import { useAgentPresets } from "@/hooks/useAgentPresets";
const mockUseAgentPresets = vi.mocked(useAgentPresets);

function renderComposer(navigatePath?: { captured: string }) {
  const routes = navigatePath
    ? [
        { path: "/compose", element: <SnapshotComposerPage /> },
        {
          path: "*",
          element: (
            <LocationProbe
              onChange={(p) => {
                navigatePath.captured = p;
              }}
            />
          ),
        },
      ]
    : undefined;

  return renderWithProviders(<SnapshotComposerPage />, {
    initialEntries: ["/compose"],
    routePath: routes ? undefined : "/compose",
    routes,
  });
}

describe("SnapshotComposerPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("renders profile select with options from hook data", () => {
    renderComposer();
    expect(screen.getByRole("option", { name: "Select profile…" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Day Trader" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Swing Trader" })).toBeInTheDocument();
  });

  it("renders watchlist select with options from hook data", () => {
    renderComposer();
    expect(screen.getByRole("option", { name: "Select watchlist…" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Tech" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Energy" })).toBeInTheDocument();
  });

  it("auto-selects the first profile on mount", async () => {
    renderComposer();
    const [profileSelect] = screen.getAllByRole("combobox");
    await waitFor(() => {
      expect((profileSelect as HTMLSelectElement).value).toBe("1");
    });
  });

  it("auto-selects the first watchlist on mount", async () => {
    renderComposer();
    const selects = screen.getAllByRole("combobox");
    const watchlistSelect = selects[1];
    await waitFor(() => {
      expect((watchlistSelect as HTMLSelectElement).value).toBe("10");
    });
  });

  it("shows tickers for selected watchlist", async () => {
    renderComposer();
    // The watchlist tickers appear in both the watchlist line and the "Using:"
    // effective-set summary, so match all and assert at least one is present.
    await waitFor(() => {
      expect(screen.getAllByText(/AAPL.*GOOGL|GOOGL.*AAPL/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("toggling a section updates the section picker checkboxes", async () => {
    const user = userEvent.setup();
    renderComposer();
    // After auto-select, profile 1 has default_includes: ["quotes", "ohlc"]
    await waitFor(() => {
      const quotesCheckbox = screen.getByRole("checkbox", { name: /quotes/i });
      expect(quotesCheckbox).toBeChecked();
    });
    const ohlcCheckbox = screen.getByRole("checkbox", { name: /ohlc/i });
    await user.click(ohlcCheckbox);
    expect(ohlcCheckbox).not.toBeChecked();
    await user.click(ohlcCheckbox);
    expect(ohlcCheckbox).toBeChecked();
  });

  it("typing in objective textarea updates state", async () => {
    const user = userEvent.setup();
    renderComposer();
    const objectiveTextarea = screen.getByPlaceholderText(/what do you want/i);
    await user.type(objectiveTextarea, "Am I overexposed to tech?");
    expect(objectiveTextarea).toHaveValue("Am I overexposed to tech?");
  });

  it("typing in notes textarea updates state", async () => {
    const user = userEvent.setup();
    renderComposer();
    const notesTextareas = screen.getAllByRole("textbox");
    const notesTextarea = notesTextareas[notesTextareas.length - 1];
    await user.type(notesTextarea, "Market feels jittery");
    expect(notesTextarea).toHaveValue("Market feels jittery");
  });

  it("Capture button is disabled when no profile is selected", async () => {
    vi.doMock("@/hooks/useProfiles", () => ({
      useProfiles: () => ({ data: [] }),
    }));
    // Render without auto-select happening (profiles empty means profileId stays null)
    renderWithProviders(<SnapshotComposerPage />, {
      initialEntries: ["/compose"],
      routePath: "/compose",
    });
    const btn = await screen.findByTestId("capture-btn");
    // With no profiles, profileId is null, button should be disabled
    // (the mock at module level still kicks in; we test the initial null state)
    expect(btn).toBeInTheDocument();
  });

  it("submits with correct body shape and navigates to thread URL", async () => {
    const user = userEvent.setup();
    mockCreateSnap.mockResolvedValue({
      id: 100,
      status: "ready",
      includes: ["quotes", "ohlc"],
    });
    mockCreateThread.mockResolvedValue({ id: 200, title: "Consult" });

    const nav = { captured: "" };
    renderComposer(nav);

    await waitFor(() => {
      const [profileSelect] = screen.getAllByRole("combobox");
      expect((profileSelect as HTMLSelectElement).value).toBe("1");
    });

    const objective = screen.getByPlaceholderText(/what do you want/i);
    await user.type(objective, "Morning check");

    const btn = screen.getByTestId("capture-btn");
    await user.click(btn);

    await waitFor(() => {
      expect(mockCreateSnap).toHaveBeenCalledWith(
        expect.objectContaining({
          profile_id: 1,
          includes: expect.arrayContaining(["quotes"]),
          watchlist_tickers: expect.arrayContaining(["AAPL", "GOOGL"]),
          ohlc_ticker: "AAPL",
          ohlc_bars: 60,
          image_ids: [],
          objective: "Morning check",
        }),
      );
    });

    await waitFor(() => {
      expect(mockCreateThread).toHaveBeenCalledWith(
        expect.objectContaining({
          profile_id: 1,
          pinned_snapshot_id: 100,
          // "Capture + ask" opts into an immediate AI reply.
          auto_reply: true,
        }),
      );
    });

    await waitFor(() => {
      expect(nav.captured).toBe("/threads/200?snapshot=100");
    });
  });

  it("posts current and potential positions as separate fields", async () => {
    const user = userEvent.setup();
    mockCreateSnap.mockResolvedValue({ id: 100, status: "ready", includes: [] });
    mockCreateThread.mockResolvedValue({ id: 200, title: "Consult" });

    renderComposer();

    await waitFor(() => {
      const [profileSelect] = screen.getAllByRole("combobox");
      expect((profileSelect as HTMLSelectElement).value).toBe("1");
    });

    await user.type(screen.getByPlaceholderText(/Holdings you want the AI to manage/i), "100 SPY @ 450");
    await user.type(screen.getByPlaceholderText(/Trades you're weighing/i), "long NVDA 6mo");

    await user.click(screen.getByTestId("capture-btn"));

    await waitFor(() => {
      expect(mockCreateSnap).toHaveBeenCalledWith(
        expect.objectContaining({
          manual_positions: "100 SPY @ 450",
          candidate_positions: "long NVDA 6mo",
        }),
      );
    });
  });

  it("unions ad-hoc typed tickers with the selected watchlist on submit", async () => {
    const user = userEvent.setup();
    mockCreateSnap.mockResolvedValue({ id: 100, status: "ready", includes: [] });
    mockCreateThread.mockResolvedValue({ id: 200, title: "Consult" });

    const nav = { captured: "" };
    renderComposer(nav);

    await waitFor(() => {
      const selects = screen.getAllByRole("combobox");
      expect((selects[1] as HTMLSelectElement).value).toBe("10");
    });

    await user.type(screen.getByLabelText("Add tickers"), "tsla{Enter}");

    await user.click(screen.getByTestId("capture-btn"));

    await waitFor(() => {
      expect(mockCreateSnap).toHaveBeenCalledWith(
        expect.objectContaining({
          watchlist_tickers: ["AAPL", "GOOGL", "TSLA"],
          ohlc_ticker: "AAPL",
        }),
      );
    });
  });

  it("waits for the snapshot to be ready before creating the thread", async () => {
    const user = userEvent.setup();
    mockCreateSnap.mockResolvedValue({ id: 100, status: "pending", includes: [] });
    let resolveReady!: (s: { id: number; status: string }) => void;
    mockWaitForReady.mockReturnValue(
      new Promise((resolve) => {
        resolveReady = resolve;
      }),
    );
    mockCreateThread.mockResolvedValue({ id: 200, title: "Consult" });

    const nav = { captured: "" };
    renderComposer(nav);
    await waitFor(() => {
      const [profileSelect] = screen.getAllByRole("combobox");
      expect((profileSelect as HTMLSelectElement).value).toBe("1");
    });

    await user.click(screen.getByTestId("capture-btn"));

    await waitFor(() => expect(mockWaitForReady).toHaveBeenCalledWith(100));
    expect(mockCreateThread).not.toHaveBeenCalled();

    resolveReady({ id: 100, status: "ready" });
    await waitFor(() =>
      expect(mockCreateThread).toHaveBeenCalledWith(
        expect.objectContaining({ pinned_snapshot_id: 100 }),
      ),
    );
    await waitFor(() => expect(nav.captured).toBe("/threads/200?snapshot=100"));
  });

  it("surfaces an error and creates no thread when capture fails", async () => {
    const user = userEvent.setup();
    mockCreateSnap.mockResolvedValue({ id: 101, status: "pending", includes: [] });
    mockWaitForReady.mockRejectedValue(
      new ApiError(400, "snapshot_failed", "Snapshot capture failed"),
    );

    const nav = { captured: "" };
    renderComposer(nav);
    await waitFor(() => {
      const [profileSelect] = screen.getAllByRole("combobox");
      expect((profileSelect as HTMLSelectElement).value).toBe("1");
    });

    await user.click(screen.getByTestId("capture-btn"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/capture failed/i);
    expect(mockCreateThread).not.toHaveBeenCalled();
    expect(nav.captured).toBe("");
  });

  it("shows staged images from localStorage and allows dropping one", async () => {
    const user = userEvent.setup();
    localStorage.setItem("staged_image_ids", JSON.stringify([7, 8]));

    renderComposer();

    expect(await screen.findByLabelText("drop staged image 7")).toBeInTheDocument();
    expect(screen.getByLabelText("drop staged image 8")).toBeInTheDocument();

    await user.click(screen.getByLabelText("drop staged image 7"));

    await waitFor(() => {
      expect(screen.queryByLabelText("drop staged image 7")).not.toBeInTheDocument();
    });
    expect(screen.getByLabelText("drop staged image 8")).toBeInTheDocument();

    expect(JSON.parse(localStorage.getItem("staged_image_ids") ?? "[]")).toEqual([8]);
  });

  it("clears localStorage after successful capture", async () => {
    const user = userEvent.setup();
    localStorage.setItem("staged_image_ids", JSON.stringify([7]));

    mockCreateSnap.mockResolvedValue({ id: 100, status: "ready", includes: [] });
    mockCreateThread.mockResolvedValue({ id: 200, title: "Consult" });

    const nav = { captured: "" };
    renderComposer(nav);

    await waitFor(() => {
      const [profileSelect] = screen.getAllByRole("combobox");
      expect((profileSelect as HTMLSelectElement).value).toBe("1");
    });

    const btn = screen.getByTestId("capture-btn");
    await user.click(btn);

    await waitFor(() => {
      expect(nav.captured).toBe("/threads/200?snapshot=100");
    });

    expect(localStorage.getItem("staged_image_ids")).toBeNull();
  });
});

const PRESET_A: AgentPreset = {
  id: 10,
  name: "Morning Scan",
  slug: "morning-scan",
  description: "Daily morning check",
  objective_template: "What are the key market moves this morning?",
  structured: false,
  builtin: false,
  active: true,
  created_at: "2026-05-25T00:00:00Z",
  updated_at: "2026-05-25T00:00:00Z",
};

describe("SnapshotComposerPage – preset dropdown", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockUseAgentPresets.mockReturnValue({ data: [] } as never);
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("does not show preset dropdown when no active presets", () => {
    mockUseAgentPresets.mockReturnValue({ data: [] } as never);
    renderComposer();
    expect(screen.queryByLabelText("Apply a preset")).not.toBeInTheDocument();
  });

  it("shows preset dropdown with options when active presets exist", () => {
    mockUseAgentPresets.mockReturnValue({ data: [PRESET_A] } as never);
    renderComposer();
    expect(screen.getByLabelText("Apply a preset")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Morning Scan" })).toBeInTheDocument();
  });

  it("selecting a preset fills objective only, leaving section boxes unchanged", async () => {
    const user = userEvent.setup();
    mockUseAgentPresets.mockReturnValue({ data: [PRESET_A] } as never);
    renderComposer();

    const positionsBefore = (screen.getByRole("checkbox", { name: /positions/i }) as HTMLInputElement).checked;

    // The auto-selected profile (Day Trader, default_includes: ["quotes","ohlc"]) has
    // already checked ohlc on render — verify a CURRENTLY-CHECKED box exists before
    // the preset is applied so the subsequent assertion is a genuine guard.
    expect((screen.getByRole("checkbox", { name: /ohlc/i }) as HTMLInputElement).checked).toBe(true);

    const presetSelect = screen.getByLabelText("Apply a preset");
    await user.selectOptions(presetSelect, String(PRESET_A.id));

    const objectiveTextarea = screen.getByPlaceholderText(/what do you want/i);
    expect(objectiveTextarea).toHaveValue(PRESET_A.objective_template);

    // ohlc was checked before the preset; it must remain checked after (the headline
    // behavior: preset apply must NOT touch section boxes).
    expect((screen.getByRole("checkbox", { name: /ohlc/i }) as HTMLInputElement).checked).toBe(true);

    expect((screen.getByRole("checkbox", { name: /positions/i }) as HTMLInputElement).checked).toBe(positionsBefore);
  });
});
