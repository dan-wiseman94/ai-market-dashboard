/**
 * ThreadDetailPage tests — interaction layer.
 *
 * Mocks all hooks that reach outside (network, WS) so tests remain fast and
 * deterministic. The two basic testid smoke-tests (compose-input, message-<id>)
 * already exist in testids/rows.test.tsx; this file focuses on interactions.
 */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "./testUtils";
import ThreadDetailPage from "@/pages/ThreadDetailPage";

// ---- Module-level mocks (hoisted by Vitest) ----

// WebSocket subscription must be a no-op (ThreadDetailPage + BranchGroup both
// call useChannel which calls ws.subscribe internally)
vi.mock("@/realtime/WebSocketProvider", () => ({
  WebSocketProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useWebSocket: () => ({ subscribe: vi.fn(() => () => {}) }),
}));

// useBranchState is called inside BranchGroup (child component).
vi.mock("@/hooks/useBranchState", () => ({
  useBranchState: () => ({ state: {}, handleEvent: vi.fn() }),
}));

const mockSendMutate = vi.fn();
const mockCompareMutate = vi.fn();
const mockStopMutate = vi.fn();
const mockRefetch = vi.fn();

// useThread and its siblings are mocked; useThread is a vi.fn() so individual
// tests can override its return value via vi.mocked(useThread).mockReturnValue.
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
}));

vi.mock("@/hooks/useSnapshot", () => ({
  useSnapshot: () => ({ data: null }),
}));

vi.mock("@/hooks/useFiles", () => ({
  useFiles: () => ({ data: [] }),
  useAttachFileToThread: () => ({ mutate: vi.fn() }),
}));

// ProviderModelPicker makes API calls — short-circuit it.
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

// ---- Import the mocked hook so we can call vi.mocked on it ----
// This import happens after the vi.mock calls above are hoisted.
import { useThread } from "@/hooks/useThread";

// ---- Fixtures ----

const defaultThread = {
  id: 42,
  title: "Morning consultation",
  kind: "consult",
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
  created_at: "2026-05-17T09:00:00Z",
};

const streamingThread = {
  ...defaultThread,
  messages: [
    {
      id: 200,
      role: "user",
      status: "done",
      content: { text: "Summarise breadth." },
      ai_run: null,
      error: null,
    },
    {
      id: 201,
      role: "assistant",
      status: "streaming",
      content: { text: "Thinking…" },
      ai_run: { cost_usd: null, model: "claude-sonnet-4-6", provider: "claude" },
      error: null,
    },
  ],
};

// ---- Render helper ----

function renderThread() {
  return renderWithProviders(<ThreadDetailPage />, {
    routePath: "/threads/:id",
    initialEntries: ["/threads/42"],
  });
}

// ---- Tests ----

describe("ThreadDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useThread).mockReturnValue({
      data: defaultThread,
      refetch: mockRefetch,
    } as unknown as ReturnType<typeof useThread>);
  });

  it("renders thread title from hook data", async () => {
    renderThread();
    expect(await screen.findByText("Morning consultation")).toBeInTheDocument();
  });

  it("renders existing user message text", async () => {
    renderThread();
    expect(await screen.findByText("What does the tape say?")).toBeInTheDocument();
  });

  it("renders existing assistant message text", async () => {
    renderThread();
    expect(await screen.findByText("The market looks oversold.")).toBeInTheDocument();
  });

  it("compose input exists with placeholder text", async () => {
    renderThread();
    const input = await screen.findByTestId("compose-input");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("placeholder", "Continue the thread…");
  });

  it("typing in compose input updates the field value", async () => {
    const user = userEvent.setup();
    renderThread();
    const input = await screen.findByTestId("compose-input");
    await user.type(input, "Is this a bull trap?");
    expect(input).toHaveValue("Is this a bull trap?");
  });

  it("submitting compose form calls useSendMessage.mutate with trimmed text", async () => {
    const user = userEvent.setup();
    mockSendMutate.mockImplementation((_args: unknown, opts: { onSuccess?: () => void }) => {
      opts?.onSuccess?.();
    });
    renderThread();
    const input = await screen.findByTestId("compose-input");
    await user.type(input, "Bull trap?");
    await user.keyboard("{Enter}");
    await waitFor(() => {
      expect(mockSendMutate).toHaveBeenCalledWith(
        expect.objectContaining({ text: "Bull trap?" }),
        expect.any(Object),
      );
    });
  });

  it("clicking Compare button shows the CompareDialog", async () => {
    const user = userEvent.setup();
    renderThread();
    const compareBtn = await screen.findByRole("button", { name: /compare/i });
    await user.click(compareBtn);
    expect(
      await screen.findByPlaceholderText("Your question to every branch…"),
    ).toBeInTheDocument();
  });

  it("StopButton visible for streaming message and calls useStopMessage.mutate on click", async () => {
    const user = userEvent.setup();
    vi.mocked(useThread).mockReturnValue({
      data: streamingThread,
      refetch: mockRefetch,
    } as unknown as ReturnType<typeof useThread>);

    renderThread();

    const stopBtn = await screen.findByRole("button", { name: /stop generation/i });
    expect(stopBtn).toBeInTheDocument();

    await user.click(stopBtn);
    expect(mockStopMutate).toHaveBeenCalledWith(201);
  });

  it("shows loading state when thread data is null", () => {
    vi.mocked(useThread).mockReturnValue({
      data: undefined,
      refetch: mockRefetch,
    } as unknown as ReturnType<typeof useThread>);
    renderThread();
    expect(screen.getByText(/loading thread/i)).toBeInTheDocument();
  });
});
