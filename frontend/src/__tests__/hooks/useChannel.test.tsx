import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const subscribeSpy = vi.fn();
// Stable context object — the real provider memoizes ctx, so useChannel's
// [channel, ws] effect must not re-run from ws identity churn in the mock.
const stableCtx = { subscribe: subscribeSpy };

vi.mock("@/realtime/WebSocketProvider", async () => {
  const mod = await vi.importActual<typeof import("@/realtime/WebSocketProvider")>("@/realtime/WebSocketProvider");
  return { ...mod, useWebSocket: () => stableCtx };
});

import { useChannel } from "@/hooks/useChannel";

beforeEach(() => {
  subscribeSpy.mockReset();
});

describe("useChannel", () => {
  it("subscribes on mount with the channel and a delegating wrapper", () => {
    subscribeSpy.mockReturnValue(() => {});
    const handler = vi.fn();
    renderHook(() => useChannel("thread.1", handler));
    expect(subscribeSpy).toHaveBeenCalledWith("thread.1", expect.any(Function));
    // The wrapper delegates to the provided handler.
    const wrapper = subscribeSpy.mock.calls[0][1] as (m: unknown) => void;
    wrapper({ event: "text_delta" });
    expect(handler).toHaveBeenCalledWith({ event: "text_delta" });
  });

  it("does NOT resubscribe when only the handler identity changes (unmemoized handler)", () => {
    // A resubscribe would tear the socket down (sole subscriber) and drop the
    // channel's replay cursor — handler identity must not churn the socket.
    const unsub = vi.fn();
    subscribeSpy.mockReturnValue(unsub);
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = renderHook(({ h }) => useChannel("thread.1", h), {
      initialProps: { h: first },
    });
    expect(subscribeSpy).toHaveBeenCalledTimes(1);
    rerender({ h: second });
    expect(subscribeSpy).toHaveBeenCalledTimes(1);
    expect(unsub).not.toHaveBeenCalled();
    // Messages arriving after the swap reach the LATEST handler.
    const wrapper = subscribeSpy.mock.calls[0][1] as (m: unknown) => void;
    wrapper({ event: "message_done" });
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith({ event: "message_done" });
  });

  it("calls unsubscribe on unmount", () => {
    const unsub = vi.fn();
    subscribeSpy.mockReturnValue(unsub);
    const { unmount } = renderHook(() => useChannel("thread.2", () => {}));
    unmount();
    expect(unsub).toHaveBeenCalled();
  });

  it("routes messages to the handler", () => {
    let captured: ((m: unknown) => void) | null = null;
    subscribeSpy.mockImplementationOnce((_ch: string, h: (m: unknown) => void) => {
      captured = h;
      return () => {};
    });
    const onMessage = vi.fn();
    renderHook(() => useChannel("thread.3", onMessage));
    captured!({ type: "tok", text: "hi" });
    expect(onMessage).toHaveBeenCalledWith({ type: "tok", text: "hi" });
  });

  it("does NOT subscribe when channel is null", () => {
    renderHook(() => useChannel(null, () => {}));
    expect(subscribeSpy).not.toHaveBeenCalled();
  });

  it("re-subscribes when channel changes", () => {
    const unsub1 = vi.fn();
    const unsub2 = vi.fn();
    subscribeSpy.mockReturnValueOnce(unsub1).mockReturnValueOnce(unsub2);
    const { rerender, unmount } = renderHook(({ ch }) => useChannel(ch, () => {}), {
      initialProps: { ch: "thread.1" as string | null },
    });
    expect(subscribeSpy).toHaveBeenCalledTimes(1);
    rerender({ ch: "thread.2" });
    expect(unsub1).toHaveBeenCalled();
    expect(subscribeSpy).toHaveBeenCalledTimes(2);
    unmount();
    expect(unsub2).toHaveBeenCalled();
  });
});
