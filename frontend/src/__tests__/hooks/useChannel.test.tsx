import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const subscribeSpy = vi.fn();

vi.mock("@/realtime/WebSocketProvider", async () => {
  const mod = await vi.importActual<typeof import("@/realtime/WebSocketProvider")>("@/realtime/WebSocketProvider");
  return { ...mod, useWebSocket: () => ({ subscribe: subscribeSpy }) };
});

import { useChannel } from "@/hooks/useChannel";

beforeEach(() => {
  subscribeSpy.mockReset();
});

describe("useChannel", () => {
  it("subscribes on mount with channel + handler", () => {
    subscribeSpy.mockReturnValue(() => {});
    const handler = vi.fn();
    renderHook(() => useChannel("thread.1", handler));
    expect(subscribeSpy).toHaveBeenCalledWith("thread.1", handler);
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
