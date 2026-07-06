import { useCallback, useMemo, useState } from "react";
import { useChannel } from "@/hooks/useChannel";
import type { Message, Thread } from "@/api/threads";
import type { ToolCallRecord } from "@/components/ToolCallTrace";
import type { LiveMessage, WsMsg } from "./types";

function toLiveMessage(m: Message): LiveMessage {
  return {
    id: m.id,
    role: m.role === "system" ? "assistant" : m.role,
    text: m.content?.text ?? "",
    status: m.status,
    error: m.error,
    cost: m.ai_run?.cost_usd,
    model: m.ai_run?.model,
    provider: m.ai_run?.provider,
    parent_message_id: m.parent_message_id ?? null,
    snapshot_id: m.snapshot_id ?? null,
    kind: m.content?.kind,
    report: m.content?.report,
  };
}

/**
 * Rebuild the live map from refetched server rows without clobbering in-flight
 * streams. A message we are actively streaming over WS holds MORE text than
 * its server row: the DB partial flush lags by up to 0.75s, and the deltas
 * covering that gap were already consumed and are never re-delivered. A
 * refetch triggered elsewhere (another Compare branch's message_done, window
 * refocus) must therefore keep the live entry while both sides are still
 * streaming. Server state wins once the row is terminal (done/failed) or when
 * `replaceAll` is set (after a replay_gap the buffered stream itself has holes).
 */
function reseed(
  prev: Record<number, LiveMessage>,
  messages: Message[],
  replaceAll: boolean,
): Record<number, LiveMessage> {
  const seed: Record<number, LiveMessage> = {};
  for (const m of messages) {
    const cur = prev[m.id];
    const keepLive = !replaceAll && cur?.status === "streaming" && m.status === "streaming";
    seed[m.id] = keepLive ? cur : toLiveMessage(m);
  }
  if (!replaceAll) {
    // A refetch snapshot can predate a just-started stream's row — don't drop
    // an in-flight bubble the server payload doesn't know about yet.
    for (const cur of Object.values(prev)) {
      if (cur.status === "streaming" && !(cur.id in seed)) seed[cur.id] = cur;
    }
  }
  return seed;
}

/**
 * Owns the live conversation state for a thread: the per-message map seeded from
 * the loaded thread, the streaming WebSocket handler, the per-message tool-call
 * traces, and the derived top-level / branch grouping.
 *
 * Subscribes to `thread.<id>` and applies the streaming event union
 * (message_started / text_delta / message_done / error|cost_capped /
 * tool_call / tool_result) exactly as the consumer requires.
 */
export function useLiveMessages(
  threadId: number | null,
  thread: Thread | undefined,
  refetch: () => void,
) {
  const [live, setLive] = useState<Record<number, LiveMessage>>({});
  // Per-assistant-message map of tool_use_id → ToolCallRecord.
  const [toolCalls, setToolCalls] = useState<
    Record<number, Record<string, ToolCallRecord>>
  >({});

  // Set by a replay_gap frame: the WS stream is known to have holes, so the
  // next reseed must take server state wholesale instead of preserving
  // buffered streaming text.
  const [resync, setResync] = useState(false);

  // ThreadDetailPage does NOT remount on a /threads/:id param change, so this
  // hook's state survives a thread switch. Reset it wholesale when the id
  // changes — the keep-streaming reseed below would otherwise re-add the old
  // thread's in-flight bubble (absent from the new thread's payload) and
  // render a frozen partial message from thread A inside thread B forever.
  const [prevThreadId, setPrevThreadId] = useState(threadId);
  if (threadId !== prevThreadId) {
    setPrevThreadId(threadId);
    setLive({});
    setToolCalls({});
    setResync(false);
  }

  // Seed the live-message map from the loaded thread. Render-phase guarded
  // update keyed on the thread object (matches the prior effect's [thread] dep)
  // instead of an effect, per react-hooks v7 (set-state-in-effect).
  const [prevThread, setPrevThread] = useState<typeof thread>(undefined);
  if (thread !== prevThread) {
    setPrevThread(thread);
    if (thread) {
      const replaceAll = resync;
      if (resync) setResync(false);
      setLive((prev) => reseed(prev, thread.messages, replaceAll));
    }
  }

  const onWs = useCallback((msg: WsMsg) => {
    if (msg.type === "replay_gap") {
      // Events were lost beyond the server's replay buffer: refetch (the
      // provider also invalidates the thread query) and let server state
      // replace the buffered stream wholesale on the next reseed.
      setResync(true);
      refetch();
      return;
    }
    if (msg.event === "message_started") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: {
          id: msg.message_id, role: "assistant", text: "", status: "streaming",
          model: msg.model, provider: msg.provider,
          parent_message_id: msg.parent_message_id ?? null,
        },
      }));
    } else if (msg.event === "text_delta") {
      setLive((prev) => {
        const cur = prev[msg.message_id] ?? {
          id: msg.message_id, role: "assistant" as const, text: "", status: "streaming" as const,
        };
        return { ...prev, [msg.message_id]: { ...cur, text: cur.text + msg.text } };
      });
    } else if (msg.event === "message_done") {
      setLive((prev) => ({
        ...prev,
        [msg.message_id]: { ...prev[msg.message_id], status: "done", cost: msg.cost_usd },
      }));
      refetch();
    } else if (msg.event === "error" || msg.event === "cost_capped") {
      // _fail() (cost-cap / no-provider / disabled) broadcasts only this event —
      // no prior message_started — so seed a complete message object when absent,
      // otherwise the bubble renders without an id/role (React key warning).
      setLive((prev) => {
        const cur = prev[msg.message_id] ?? {
          id: msg.message_id, role: "assistant" as const, text: "",
        };
        return {
          ...prev,
          [msg.message_id]: {
            ...cur, id: msg.message_id, role: cur.role ?? "assistant",
            status: "failed", error: msg.error,
          },
        };
      });
    } else if (msg.event === "tool_call") {
      setToolCalls((prev) => {
        const bucket = { ...(prev[msg.message_id] ?? {}) };
        bucket[msg.tool_use_id] = {
          toolUseId: msg.tool_use_id,
          name: msg.name,
          input: msg.input,
          ok: true,
          latencyMs: 0,
        };
        return { ...prev, [msg.message_id]: bucket };
      });
    } else if (msg.event === "tool_result") {
      setToolCalls((prev) => {
        const bucket = { ...(prev[msg.message_id] ?? {}) };
        const existing = bucket[msg.tool_use_id];
        if (existing) {
          bucket[msg.tool_use_id] = {
            ...existing,
            ok: !!msg.ok,
            latencyMs: msg.latency_ms ?? 0,
          };
        }
        return { ...prev, [msg.message_id]: bucket };
      });
    }
  }, [refetch]);

  useChannel(threadId ? `thread.${threadId}` : null, onWs);

  const { ordered, branchesByParent } = useMemo(() => {
    const arr = Object.values(live).sort((a, b) => a.id - b.id);
    const byParent: Record<number, LiveMessage[]> = {};
    const top: LiveMessage[] = [];
    for (const m of arr) {
      if (m.role === "assistant" && m.parent_message_id != null) {
        (byParent[m.parent_message_id] ??= []).push(m);
      } else {
        top.push(m);
      }
    }
    return { ordered: top, branchesByParent: byParent };
  }, [live]);

  return { ordered, branchesByParent, toolCalls };
}
