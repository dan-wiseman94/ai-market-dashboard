import { useCallback, useReducer } from "react";

export type BranchEvent =
  | { event: "message_started"; message_id: number; parent_message_id: number | null; provider: string; model: string }
  | { event: "message_done"; message_id: number; cost_usd: string }
  | { event: "cost"; message_id: number; parent_message_id: number | null;
      cost_usd: string; tokens_in: number; tokens_out: number; tokens_cached: number; duration_ms: number }
  | { event: "error"; message_id: number; error: string };

export type BranchState = {
  status: "streaming" | "done" | "failed";
  provider?: string;
  model?: string;
  cost?: number;
  tokensIn?: number;
  tokensOut?: number;
  tokensCached?: number;
  durationMs?: number;
};

type State = Record<number, BranchState>;

function reducer(state: State, ev: BranchEvent & { parentId: number }): State {
  const id = ev.message_id;
  const prev = state[id] ?? { status: "streaming" as const };
  switch (ev.event) {
    case "message_started":
      return { ...state, [id]: { ...prev, status: "streaming", provider: ev.provider, model: ev.model } };
    case "cost":
      return {
        ...state,
        [id]: {
          ...prev,
          status: "done",
          cost: Number(ev.cost_usd),
          tokensIn: ev.tokens_in,
          tokensOut: ev.tokens_out,
          tokensCached: ev.tokens_cached,
          durationMs: ev.duration_ms,
        },
      };
    case "error":
      return { ...state, [id]: { ...prev, status: "failed" } };
    case "message_done":
      return state;
    default:
      return state;
  }
}

export function useBranchState(parentMessageId: number) {
  const [state, dispatch] = useReducer(reducer, {} as State);
  const handleEvent = useCallback((ev: BranchEvent) => {
    if ("parent_message_id" in ev && ev.parent_message_id !== parentMessageId) return;
    if (ev.event === "message_done") return;
    dispatch({ ...ev, parentId: parentMessageId });
  }, [parentMessageId]);
  return { state, handleEvent };
}
