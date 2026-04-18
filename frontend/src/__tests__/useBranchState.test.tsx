import { act, renderHook } from "@testing-library/react";
import { useBranchState, type BranchEvent } from "@/hooks/useBranchState";

test("tracks per-branch status, cost, and duration", () => {
  const { result } = renderHook(() => useBranchState(42));

  act(() => {
    result.current.handleEvent({
      event: "message_started",
      message_id: 101,
      parent_message_id: 42,
      provider: "claude",
      model: "claude-sonnet-4-6",
    } as BranchEvent);
  });

  expect(result.current.state[101]).toMatchObject({
    status: "streaming",
    provider: "claude",
    model: "claude-sonnet-4-6",
  });

  act(() => {
    result.current.handleEvent({
      event: "cost",
      message_id: 101,
      parent_message_id: 42,
      cost_usd: "0.0123",
      tokens_in: 1000,
      tokens_out: 100,
      tokens_cached: 0,
      duration_ms: 1800,
    } as BranchEvent);
  });

  expect(result.current.state[101]).toMatchObject({
    status: "done",
    cost: 0.0123,
    tokensIn: 1000,
    tokensOut: 100,
    durationMs: 1800,
  });
});

test("ignores events for other parent messages", () => {
  const { result } = renderHook(() => useBranchState(42));
  act(() => {
    result.current.handleEvent({
      event: "message_started",
      message_id: 999,
      parent_message_id: 7,
      provider: "openai",
      model: "gpt-5",
    } as BranchEvent);
  });
  expect(result.current.state).toEqual({});
});
