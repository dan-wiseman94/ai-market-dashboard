/**
 * The normalized event union broadcast on the `thread.<id>` WebSocket channel.
 *
 * The backend emits a closed set of events (the `_broadcast` sites in
 * apps/threads/tasks.py and apps/threads/_stream.py), each stamped with a
 * monotonic `seq` by apps/threads/event_log.py. `replay_gap` is the one
 * seq-less frame: the consumer sends it when a reconnect's `?since=` falls
 * outside the replay buffer, meaning events were lost and server state must be
 * refetched instead of trusting the stream.
 *
 * Every member carries `type?: undefined` / `event?: undefined` markers so a
 * handler can narrow on either discriminant with plain `===` checks.
 */

type ThreadEvent<E extends string, Fields> = Fields & {
  event: E;
  message_id: number;
  seq?: number;
  type?: undefined;
};

export type ThreadWsMsg =
  | ThreadEvent<
      "message_started",
      { parent_message_id: number | null; provider: string; model: string }
    >
  | ThreadEvent<"text_delta", { text: string }>
  | ThreadEvent<"thinking_delta", { text: string }>
  | ThreadEvent<"message_done", { cost_usd: string }>
  | ThreadEvent<
      "cost",
      {
        parent_message_id: number | null;
        cost_usd: string;
        tokens_in: number;
        tokens_out: number;
        tokens_cached: number;
        duration_ms: number;
      }
    >
  | ThreadEvent<"error", { error: string }>
  | ThreadEvent<"cost_capped", { error: string }>
  | ThreadEvent<"warning", { text: string }>
  | ThreadEvent<"tool_call", { tool_use_id: string; name: string; input: unknown }>
  | ThreadEvent<"tool_result", { tool_use_id: string; ok: boolean; latency_ms: number }>
  | { type: "replay_gap"; event?: undefined; message_id?: undefined; seq?: number };
