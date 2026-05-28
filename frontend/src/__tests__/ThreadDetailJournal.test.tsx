/**
 * ThreadDetailPage — Close & journal panel tests.
 *
 * Tests the journal panel, inline entries, and promote-to-thesis flow.
 * Mirrors the mock pattern from ThreadDetailPage.test.tsx (same module mocks).
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "./testUtils";
import ThreadDetailPage from "@/pages/ThreadDetailPage";
import type { JournalEntry } from "@/api/journal";

// ---- Module-level mocks (must mirror ThreadDetailPage.test.tsx) ----

vi.mock("@/realtime/WebSocketProvider", () => ({
  WebSocketProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useWebSocket: () => ({ subscribe: vi.fn(() => () => {}) }),
}));

vi.mock("@/hooks/useBranchState", () => ({
  useBranchState: () => ({ state: {}, handleEvent: vi.fn() }),
}));

const mockSendMutate = vi.fn();
const mockCompareMutate = vi.fn();
const mockStopMutate = vi.fn();
const mockRefetch = vi.fn();

vi.mock("@/hooks/useThread", () => ({
  useThread: vi.fn(),
  useSendMessage: vi.fn(() => ({
    mutate: mockSendMutate,
    mutateAsync: vi.fn(),
    isPending: false,
  })),
  useCompareMessage: vi.fn(() => ({
    mutate: mockCompareMutate,
    mutateAsync: vi.fn(),
    isPending: false,
  })),
  useStopMessage: vi.fn(() => ({
    mutate: mockStopMutate,
    mutateAsync: vi.fn(),
    isPending: false,
  })),
  useRenameThread: vi.fn(() => ({
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
  })),
}));

vi.mock("@/hooks/useSnapshot", () => ({
  useSnapshot: () => ({ data: null }),
}));

vi.mock("@/hooks/useFiles", () => ({
  useFiles: () => ({ data: [] }),
  useAttachFileToThread: () => ({ mutate: vi.fn() }),
}));

vi.mock("@/hooks/useAiModels", () => ({
  useAiModels: () => ({
    data: {
      models: [
        {
          id: "claude-sonnet-4-6",
          name: "Claude Sonnet 4.6",
          provider: "claude",
          input_per_mtok: 3,
          output_per_mtok: 15,
          cached_per_mtok: 0.3,
          context_window: 200000,
          supports_vision: true,
        },
      ],
    },
  }),
}));

// Journal hooks — controlled per test
const mockJournalMutate = vi.fn();
const mockJournalMutateAsync = vi.fn();
vi.mock("@/hooks/useJournal", () => ({
  useJournal: vi.fn(() => ({ data: [] })),
  useCreateJournalEntry: vi.fn(() => ({
    mutate: mockJournalMutate,
    mutateAsync: mockJournalMutateAsync,
    isPending: false,
  })),
}));

// Thesis creation — controlled per test
const mockThesisMutate = vi.fn();
vi.mock("@/hooks/useTheses", () => ({
  useCreateThesis: vi.fn(() => ({
    mutate: mockThesisMutate,
    mutateAsync: vi.fn(),
    isPending: false,
  })),
}));

// ---- Import mocked hooks for vi.mocked() ----
import { useThread } from "@/hooks/useThread";
import { useJournal } from "@/hooks/useJournal";

// ---- Fixtures ----

const defaultThread = {
  id: 42,
  title: "Morning consultation",
  kind: "consult",
  pinned_snapshot_id: 5,
  profile: { id: 1, name: "Day Trader" },
  messages: [
    {
      id: 100,
      role: "user",
      status: "done",
      content: { text: "What does the tape say?" },
      ai_run: null,
      error: null,
    },
    {
      id: 101,
      role: "assistant",
      status: "done",
      content: { text: "The market looks oversold." },
      ai_run: { cost_usd: "0.002", model: "claude-sonnet-4-6", provider: "claude" },
      error: null,
    },
  ],
  created_at: "2026-05-25T09:00:00Z",
};

const journalEntries: JournalEntry[] = [
  {
    id: 10,
    thread_id: 42,
    thesis_id: null,
    snapshot_id: 5,
    decision: "passed",
    note: "Macro too uncertain.",
    created_at: "2026-05-25T08:00:00Z",
  },
  {
    id: 11,
    thread_id: 42,
    thesis_id: 7,
    snapshot_id: null,
    decision: "acted",
    note: "Went long, created thesis.",
    created_at: "2026-05-24T10:00:00Z",
  },
];

// ---- Render helper ----

function renderThread() {
  return renderWithProviders(<ThreadDetailPage />, {
    routePath: "/threads/:id",
    initialEntries: ["/threads/42"],
  });
}

// ---- Tests ----

describe("ThreadDetailPage — Close & journal panel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useThread).mockReturnValue({
      data: defaultThread,
      refetch: mockRefetch,
    } as unknown as ReturnType<typeof useThread>);
    vi.mocked(useJournal).mockReturnValue({ data: [] } as unknown as ReturnType<typeof useJournal>);
  });

  it("renders the 'Close & journal' toggle button", async () => {
    renderThread();
    const btn = await screen.findByTestId("journal-panel-btn");
    expect(btn).toBeInTheDocument();
  });

  it("panel is hidden by default", async () => {
    renderThread();
    await screen.findByTestId("journal-panel-btn");
    expect(screen.queryByTestId("journal-panel")).not.toBeInTheDocument();
  });

  it("clicking the toggle button shows the journal panel", async () => {
    const user = userEvent.setup();
    renderThread();
    const btn = await screen.findByTestId("journal-panel-btn");
    await user.click(btn);
    expect(await screen.findByTestId("journal-panel")).toBeInTheDocument();
  });

  it("'Log decision' button POSTs to /api/journal/ with thread_id and decision", async () => {
    const user = userEvent.setup();

    mockJournalMutate.mockImplementation(
      (_args: unknown, opts: { onSuccess?: () => void }) => {
        opts?.onSuccess?.();
      },
    );

    renderThread();
    await user.click(await screen.findByTestId("journal-panel-btn"));

    // Select "watching" from the decision selector
    const select = await screen.findByTestId("journal-decision-select");
    await user.selectOptions(select, "watching");

    // Type a note
    const noteArea = await screen.findByTestId("journal-note-textarea");
    await user.type(noteArea, "Keeping an eye on this.");

    // Click Log decision
    await user.click(await screen.findByTestId("journal-log-btn"));

    await waitFor(() => {
      expect(mockJournalMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          thread_id: 42,
          decision: "watching",
          note: "Keeping an eye on this.",
          snapshot_id: 5,
        }),
        expect.any(Object),
      );
    });
  });

  it("shows EmptyState when there are no journal entries", async () => {
    const user = userEvent.setup();
    vi.mocked(useJournal).mockReturnValue({ data: [] } as unknown as ReturnType<typeof useJournal>);

    renderThread();
    await user.click(await screen.findByTestId("journal-panel-btn"));

    expect(await screen.findByText(/no decisions logged yet/i)).toBeInTheDocument();
  });

  it("renders existing journal entries inline when panel is open", async () => {
    const user = userEvent.setup();
    vi.mocked(useJournal).mockReturnValue({ data: journalEntries } as unknown as ReturnType<typeof useJournal>);

    renderThread();
    await user.click(await screen.findByTestId("journal-panel-btn"));

    const list = await screen.findByTestId("journal-entries-list");
    expect(list).toBeInTheDocument();

    // Both entries appear
    expect(await screen.findByTestId("journal-entry-10")).toBeInTheDocument();
    expect(await screen.findByTestId("journal-entry-11")).toBeInTheDocument();

    // Notes visible
    expect(screen.getByText("Macro too uncertain.")).toBeInTheDocument();
    expect(screen.getByText("Went long, created thesis.")).toBeInTheDocument();
  });

  it("renders a thesis link for entries that have thesis_id", async () => {
    const user = userEvent.setup();
    vi.mocked(useJournal).mockReturnValue({ data: journalEntries } as unknown as ReturnType<typeof useJournal>);

    renderThread();
    await user.click(await screen.findByTestId("journal-panel-btn"));

    // Entry 11 has thesis_id = 7
    const link = await screen.findByTestId("journal-thesis-link-11");
    expect(link).toHaveAttribute("href", "/theses/7");

    // Entry 10 has no thesis_id — no link
    expect(screen.queryByTestId("journal-thesis-link-10")).not.toBeInTheDocument();
  });

  it("'Promote to thesis' button shows the thesis form with 'Promote to thesis' heading", async () => {
    const user = userEvent.setup();
    renderThread();
    await user.click(await screen.findByTestId("journal-panel-btn"));
    await user.click(await screen.findByTestId("journal-promote-btn"));

    // The thesis form should now appear
    const form = await screen.findByTestId("new-thesis-form");
    expect(form).toBeInTheDocument();
    // The form heading (eyebrow div inside the form) should say "Promote to thesis"
    expect(form.querySelector(".ledger-eyebrow")).toHaveTextContent("Promote to thesis");
  });

  it("promote-to-thesis creates a thesis AND a linked journal entry", async () => {
    const user = userEvent.setup();

    // Thesis creation succeeds and returns an object with id 99
    mockThesisMutate.mockImplementation(
      (_args: unknown, opts: { onSuccess?: (data: { id: number; title: string }) => void }) => {
        opts?.onSuccess?.({ id: 99, title: "SPY 600 Thesis" });
      },
    );

    renderThread();

    // Open journal panel
    await user.click(await screen.findByTestId("journal-panel-btn"));

    // Fill in a note so the promote-linked entry uses it
    const noteArea = await screen.findByTestId("journal-note-textarea");
    await user.type(noteArea, "Acting on this thesis.");

    // Promote to thesis
    await user.click(await screen.findByTestId("journal-promote-btn"));

    // Fill in required thesis fields
    const titleInput = await screen.findByLabelText(/title/i);
    await user.type(titleInput, "SPY 600 Thesis");
    const tickerInput = await screen.findByLabelText(/ticker/i);
    await user.type(tickerInput, "SPY");

    // Submit the thesis form
    await user.click(screen.getByRole("button", { name: /create thesis/i }));

    // Thesis should have been mutated
    await waitFor(() => {
      expect(mockThesisMutate).toHaveBeenCalled();
    });

    // Journal entry linked to thesis_id 99 should also have been created
    await waitFor(() => {
      expect(mockJournalMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          thread_id: 42,
          thesis_id: 99,
        }),
        expect.any(Object),
      );
    });
  });

  it("promote-to-thesis: journal POST failure shows error toast while thesis-created toast still fired", async () => {
    const user = userEvent.setup();

    // Thesis creation succeeds
    mockThesisMutate.mockImplementation(
      (_args: unknown, opts: { onSuccess?: (data: { id: number; title: string }) => void }) => {
        opts?.onSuccess?.({ id: 77, title: "Failing Journal Thesis" });
      },
    );

    // Journal creation invokes onError
    mockJournalMutate.mockImplementation(
      (_args: unknown, opts: { onError?: () => void }) => {
        opts?.onError?.();
      },
    );

    renderThread();

    // Open journal panel
    await user.click(await screen.findByTestId("journal-panel-btn"));

    // Promote to thesis
    await user.click(await screen.findByTestId("journal-promote-btn"));

    // Fill in required thesis fields
    await user.type(await screen.findByLabelText(/title/i), "Failing Journal Thesis");
    await user.type(await screen.findByLabelText(/ticker/i), "SPY");

    // Submit
    await user.click(screen.getByRole("button", { name: /create thesis/i }));

    // Thesis-created success toast should appear
    await waitFor(() => {
      expect(screen.getByTestId("toast-success")).toHaveTextContent(/thesis created/i);
    });

    // Journal-failure error toast should also appear
    await waitFor(() => {
      expect(screen.getByTestId("toast-error")).toHaveTextContent(
        "Thesis created, but journaling the decision failed.",
      );
    });
  });

  it("plain 'New thesis from this' (new-thesis-btn) still works without logging a journal entry", async () => {
    const user = userEvent.setup();

    mockThesisMutate.mockImplementation(
      (_args: unknown, opts: { onSuccess?: (data: { id: number; title: string }) => void }) => {
        opts?.onSuccess?.({ id: 55, title: "Standalone Thesis" });
      },
    );

    renderThread();

    // Click the original button (NOT promote)
    await user.click(await screen.findByTestId("new-thesis-btn"));
    expect(await screen.findByTestId("new-thesis-form")).toBeInTheDocument();

    // Fill & submit
    await user.type(await screen.findByLabelText(/title/i), "Standalone Thesis");
    await user.type(await screen.findByLabelText(/ticker/i), "AAPL");
    await user.click(screen.getByRole("button", { name: /create thesis/i }));

    await waitFor(() => expect(mockThesisMutate).toHaveBeenCalled());

    // Journal entry must NOT have been posted
    expect(mockJournalMutate).not.toHaveBeenCalled();
  });
});
