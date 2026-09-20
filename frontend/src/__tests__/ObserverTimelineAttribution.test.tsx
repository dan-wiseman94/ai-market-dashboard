import { describe, it, expect, beforeEach, vi } from "vitest";
import { screen, waitFor, fireEvent, within } from "@testing-library/react";
import { mockApi, renderWithProviders } from "./testUtils";
import ObserverTimelinePage from "@/pages/ObserverTimelinePage";

vi.mock("html2canvas", () => ({
  default: vi.fn(() => Promise.resolve({ toDataURL: () => "data:image/png;base64,x" })),
}));

const CONSENSUS = {
  n_providers: 3,
  bias_agreement: 0.6667,
  modal_bias: "bullish",
  divergent: true,
  per_ticker: {},
  note: "",
  takes: [
    { provider: "claude", model: "claude-opus-5", bias: "bullish", signal_bias: {} },
    { provider: "openai", model: "gpt-5.6-sol", bias: "bullish", signal_bias: {} },
    { provider: "local", model: "llama3", bias: "bearish", signal_bias: {} },
  ],
};

const THREAD = {
  id: 7,
  kind: "observer",
  profile_id: 1,
  title: "Observer: P",
  messages: [
    {
      id: 1, role: "user", content: { text: "Snapshot 1" }, status: "done", error: "",
      ai_run: null, created_at: "2026-04-17T09:35:00Z",
    },
    {
      id: 2, role: "assistant", content: { text: "AI response 1" }, status: "done", error: "",
      ai_run: { provider: "openai", model: "gpt-5.6-sol", cost_usd: "0.012300" },
      created_at: "2026-04-17T09:35:05Z",
    },
    {
      id: 3, role: "assistant", status: "done", error: "", ai_run: null,
      content: {
        kind: "structured_observation",
        provider: "claude",
        model: "claude-opus-5",
        report: {
          headline: "Range day", bias: "neutral", summary: "Chop.",
          signals: [], key_levels: [], risks: [], next_check_in: "close",
        },
      },
      created_at: "2026-04-17T09:36:00Z",
    },
    {
      id: 4, role: "assistant", status: "done", error: "", ai_run: null,
      content: { kind: "consensus_report", report: CONSENSUS },
      created_at: "2026-04-17T09:37:00Z",
    },
    {
      id: 5, role: "system", status: "done", error: "",
      content: { text: "Observer fire skipped at 09:38 UTC: cost cap exceeded — daily" },
      ai_run: null, created_at: "2026-04-17T09:38:00Z",
    },
    {
      id: 6, role: "assistant", status: "failed", error: "boom",
      content: { text: "Structured run failed: boom" }, ai_run: null,
      created_at: "2026-04-17T09:39:00Z",
    },
  ],
};

beforeEach(() => {
  mockApi({ "GET /api/observer/threads/1/": THREAD });
});

function renderPage() {
  return renderWithProviders(<ObserverTimelinePage />, {
    initialEntries: ["/threads/observer/1"],
    routePath: "/threads/observer/:profileId",
  });
}

describe("ObserverTimelinePage — attribution and kinds", () => {
  it("attributes each fire to the provider that ran it", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/Observer: P/)).toBeInTheDocument());
    const pills = screen.getAllByTestId("ai-attribution").map((e) => e.textContent);
    expect(pills).toEqual(
      expect.arrayContaining([
        "OpenAI · gpt-5.6-sol · $0.0123",
        "Claude · claude-opus-5",
      ]),
    );
  });

  it("names a consensus fire and opens its card", async () => {
    renderPage();
    const header = await screen.findByRole("button", {
      name: /Consensus — bullish · 3 providers/,
    });
    fireEvent.click(header);
    expect(screen.getByText("2 of 3 agree (67%)")).toBeInTheDocument();
  });

  it("renders a cost-cap skip as a notice, not as an answer", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText(/Observer: P/)).toBeInTheDocument());
    const notice = screen.getByText(/🔒 Observer fire skipped/);
    expect(notice).toBeInTheDocument();
    // A notice carries no model attribution — nothing ran.
    expect(within(notice.closest("li")!).queryByTestId("ai-attribution")).toBeNull();
  });

  it("flags a failed fire and shows its error when opened", async () => {
    renderPage();
    const header = await screen.findByRole("button", { name: /⚠️ Failed/ });
    expect(within(header.closest("li")!).getByText("failed")).toBeInTheDocument();
    fireEvent.click(header);
    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("marks a reused observation so it is not read as a fresh call", async () => {
    mockApi({
      "GET /api/observer/threads/1/": {
        ...THREAD,
        messages: [
          {
            id: 9, role: "assistant", status: "done", error: "", ai_run: null,
            content: { kind: "cached_observation", text: "Reused prior observation." },
            created_at: "2026-04-17T09:40:00Z",
          },
        ],
      },
    });
    renderPage();
    expect(await screen.findByRole("button", { name: /Cached observation/ })).toBeInTheDocument();
  });

  it("still shows a structured card under its headline", async () => {
    renderPage();
    const header = await screen.findByRole("button", { name: /Range day/ });
    fireEvent.click(header);
    expect(screen.getByText("Chop.")).toBeInTheDocument();
  });
});
