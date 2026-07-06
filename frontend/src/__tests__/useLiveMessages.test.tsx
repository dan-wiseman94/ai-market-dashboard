import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, it, expect, vi } from "vitest";
import type { Thread, Message } from "@/api/threads";
import type { ObservationReport } from "@/components/ObservationReportCard";

// Mock useChannel to capture the WS handler so tests can feed thread events
// without a real socket.
let wsHandler: ((msg: unknown) => void) | null = null;
vi.mock("@/hooks/useChannel", () => ({
  useChannel: (_channel: string | null, handler: (msg: unknown) => void) => {
    wsHandler = handler;
  },
}));

import { useLiveMessages } from "@/pages/thread-detail/useLiveMessages";

beforeEach(() => {
  wsHandler = null;
});

const REPORT: ObservationReport = {
  headline: "SPY consolidates near highs",
  bias: "bullish",
  summary: "Momentum is intact.",
  signals: [],
  key_levels: [],
  risks: ["Fed meeting"],
  next_check_in: "after 14:00 breadth",
};

function makeMsg(id: number, status: Message["status"], text: string): Message {
  return {
    id,
    role: "assistant",
    content: { text },
    status,
    error: "",
    created_at: "2026-01-01T00:00:00Z",
    parent_message_id: null,
    snapshot_id: null,
  };
}

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
        parent_message_id: null,
        snapshot_id: null,
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
        parent_message_id: null,
        snapshot_id: null,
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
        parent_message_id: null,
        snapshot_id: null,
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

function streamMessage(id: number, chunks: string[]): void {
  act(() => {
    wsHandler!({
      event: "message_started", message_id: id, parent_message_id: null,
      provider: "claude", model: "m",
    });
    for (const text of chunks) wsHandler!({ event: "text_delta", message_id: id, text });
  });
}

describe("useLiveMessages — refetch reseed vs in-flight streams", () => {
  it("keeps buffered streaming text when the server row is a stale mid-stream flush", () => {
    const { result, rerender } = renderHook(
      ({ thread }) => useLiveMessages(1, thread, vi.fn()),
      { initialProps: { thread: makeThread([makeMsg(10, "done", "Earlier answer.")]) } },
    );
    // Message 11 streams over WS; the deltas are consumed and never re-delivered.
    streamMessage(11, ["Hello ", "world"]);
    // Another branch's message_done (or a window refocus) refetches: the server
    // row for 11 only holds the last 0.75s partial flush.
    rerender({
      thread: makeThread([
        makeMsg(10, "done", "Earlier answer."),
        makeMsg(11, "streaming", "Hel"),
      ]),
    });
    const live = result.current.ordered.find((m) => m.id === 11)!;
    expect(live.text).toBe("Hello world"); // not clobbered back to "Hel"
    expect(live.status).toBe("streaming");
  });

  it("lets a terminal server row replace the buffered stream on reseed", () => {
    const { result, rerender } = renderHook(
      ({ thread }) => useLiveMessages(1, thread, vi.fn()),
      { initialProps: { thread: makeThread([]) } },
    );
    streamMessage(11, ["Hello "]);
    rerender({ thread: makeThread([makeMsg(11, "done", "Hello world — final.")]) });
    const live = result.current.ordered.find((m) => m.id === 11)!;
    expect(live.text).toBe("Hello world — final.");
    expect(live.status).toBe("done");
  });

  it("keeps an in-flight stream the refetched payload does not include yet", () => {
    const { result, rerender } = renderHook(
      ({ thread }) => useLiveMessages(1, thread, vi.fn()),
      { initialProps: { thread: makeThread([makeMsg(10, "done", "Earlier.")]) } },
    );
    streamMessage(12, ["mid-flight"]);
    // A refetch snapshot raced the new row's creation — 12 is absent.
    rerender({ thread: makeThread([makeMsg(10, "done", "Earlier.")]) });
    const live = result.current.ordered.find((m) => m.id === 12)!;
    expect(live.text).toBe("mid-flight");
    expect(live.status).toBe("streaming");
  });

  it("does not leak an in-flight stream (or its tool calls) across a thread switch", () => {
    // ThreadDetailPage does not remount on a /threads/:id param change, so the
    // hook's state persists across the switch and must reset itself.
    const { result, rerender } = renderHook(
      ({ threadId, thread }) => useLiveMessages(threadId, thread, vi.fn()),
      {
        initialProps: {
          threadId: 1 as number,
          thread: makeThread([makeMsg(10, "done", "Thread A history.")]),
        },
      },
    );
    streamMessage(11, ["partial from thread A"]);
    act(() => {
      wsHandler!({
        event: "tool_call", message_id: 11, tool_use_id: "t1",
        name: "get_quote", input: {},
      });
    });
    // Navigate to thread B: its payload knows nothing about message 11.
    const threadB = { ...makeThread([makeMsg(20, "done", "Thread B history.")]), id: 2 };
    rerender({ threadId: 2, thread: threadB });
    expect(result.current.ordered.map((m) => m.id)).toEqual([20]);
    expect(result.current.toolCalls).toEqual({});
  });

  it("replay_gap refetches and lets server state replace the buffered stream wholesale", () => {
    const refetch = vi.fn();
    const { result, rerender } = renderHook(
      ({ thread }) => useLiveMessages(1, thread, refetch),
      { initialProps: { thread: makeThread([]) } },
    );
    streamMessage(11, ["Hello ", "world"]);
    // The reconnect's ?since= fell outside the replay buffer: deltas were lost,
    // so the buffered text can no longer be trusted.
    act(() => wsHandler!({ type: "replay_gap" }));
    expect(refetch).toHaveBeenCalled();
    rerender({ thread: makeThread([makeMsg(11, "streaming", "Hel")]) });
    const live = result.current.ordered.find((m) => m.id === 11)!;
    expect(live.text).toBe("Hel"); // server state wins after a gap
  });

  it("replay_gap resync is scoped to streams that were in flight at gap time", () => {
    const refetch = vi.fn();
    const { result, rerender } = renderHook(
      ({ thread }) => useLiveMessages(1, thread, refetch),
      { initialProps: { thread: makeThread([]) } },
    );
    streamMessage(11, ["holed "]); // buffered text has holes after the gap
    act(() => wsHandler!({ type: "replay_gap" }));
    // A stream started AFTER the gap is clean — post-gap deltas were all
    // delivered (the provider reset its cursor), so its live text must survive
    // the gap-triggered reseed even though 11's must not.
    streamMessage(12, ["clean and complete"]);
    rerender({
      thread: makeThread([
        makeMsg(11, "streaming", "holed but fuller"),
        makeMsg(12, "streaming", "clea"),
      ]),
    });
    expect(result.current.ordered.find((m) => m.id === 11)!.text).toBe("holed but fuller");
    expect(result.current.ordered.find((m) => m.id === 12)!.text).toBe("clean and complete");
  });

  it("a stale armed replay_gap flag cannot clobber a later unrelated stream", () => {
    const refetch = vi.fn();
    const { result, rerender } = renderHook(
      ({ thread }) => useLiveMessages(1, thread, refetch),
      { initialProps: { thread: makeThread([makeMsg(10, "done", "History.")]) } },
    );
    streamMessage(11, ["holed"]);
    act(() => wsHandler!({ type: "replay_gap" }));
    // The gap-triggered refetch returned structurally identical data: react-query
    // keeps the same object, so NO reseed runs and the resync stays armed.
    // Message 11 then completes and a fresh stream 12 starts.
    act(() => wsHandler!({ event: "message_done", message_id: 11, cost_usd: "0.01" }));
    streamMessage(12, ["fresh stream"]);
    // A later unrelated reseed (e.g. another branch's message_done refetch) must
    // NOT wholesale-replace 12's live text just because the flag was never consumed.
    rerender({
      thread: makeThread([
        makeMsg(10, "done", "History."),
        makeMsg(11, "done", "holed — final."),
        makeMsg(12, "streaming", "fre"),
      ]),
    });
    const live = result.current.ordered.find((m) => m.id === 12)!;
    expect(live.text).toBe("fresh stream");
    expect(live.status).toBe("streaming");
  });
});
