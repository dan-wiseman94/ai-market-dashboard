import { renderHook } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type { Thread, Message } from "@/api/threads";
import type { ObservationReport } from "@/components/ObservationReportCard";

// Mock useChannel so it is a no-op — we only test the seed path, not WS events.
vi.mock("@/hooks/useChannel", () => ({
  useChannel: () => undefined,
}));

import { useLiveMessages } from "@/pages/thread-detail/useLiveMessages";

const REPORT: ObservationReport = {
  headline: "SPY consolidates near highs",
  bias: "bullish",
  summary: "Momentum is intact.",
  signals: [],
  key_levels: [],
  risks: ["Fed meeting"],
  next_check_in: "after 14:00 breadth",
};

function makeThread(messages: Message[]): Thread {
  return {
    id: 1,
    kind: "consult",
    title: "Test Thread",
    profile: null,
    pinned_snapshot_id: null,
    created_at: "2026-01-01T00:00:00Z",
    messages,
  };
}

describe("useLiveMessages — seed mapping", () => {
  it("maps a normal assistant message to text only (no kind/report)", () => {
    const thread = makeThread([
      {
        id: 10,
        role: "assistant",
        content: { text: "Market looks stable." },
        status: "done",
        error: "",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    const { result } = renderHook(() =>
      useLiveMessages(1, thread, vi.fn()),
    );

    const msg = result.current.ordered.find((m) => m.id === 10);
    expect(msg).toBeDefined();
    expect(msg!.text).toBe("Market looks stable.");
    expect(msg!.kind).toBeUndefined();
    expect(msg!.report).toBeUndefined();
  });

  it("maps a structured_observation message to kind='structured_observation' and report", () => {
    const thread = makeThread([
      {
        id: 20,
        role: "assistant",
        content: {
          kind: "structured_observation",
          report: REPORT,
        },
        status: "done",
        error: "",
        created_at: "2026-01-01T00:01:00Z",
      },
    ]);

    const { result } = renderHook(() =>
      useLiveMessages(1, thread, vi.fn()),
    );

    const msg = result.current.ordered.find((m) => m.id === 20);
    expect(msg).toBeDefined();
    expect(msg!.kind).toBe("structured_observation");
    expect(msg!.report).toEqual(REPORT);
    // headline is a field in the report; confirm it survived the mapping
    expect(msg!.report!.headline).toBe("SPY consolidates near highs");
  });

  it("maps system role to assistant role in LiveMessage", () => {
    const thread = makeThread([
      {
        id: 30,
        role: "system",
        content: { text: "Cost cap reached." },
        status: "done",
        error: "",
        created_at: "2026-01-01T00:02:00Z",
      },
    ]);

    const { result } = renderHook(() =>
      useLiveMessages(1, thread, vi.fn()),
    );

    const msg = result.current.ordered.find((m) => m.id === 30);
    expect(msg).toBeDefined();
    expect(msg!.role).toBe("assistant");
  });
});
