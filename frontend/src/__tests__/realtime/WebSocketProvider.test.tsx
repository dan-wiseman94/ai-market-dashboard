import { useEffect } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render } from "@testing-library/react";
import { WebSocketProvider, useWebSocket } from "@/realtime/WebSocketProvider";
import { installFakeWebSocket, type FakeWebSocketController } from "../testUtils";

let fake: FakeWebSocketController;

function TestConsumer({ channel, onMsg }: { channel: string; onMsg: (m: unknown) => void }) {
  const { subscribe } = useWebSocket();
  useEffect(() => subscribe(channel, onMsg), [subscribe, channel, onMsg]);
  return null;
}

function BadComponent() {
  useWebSocket();
  return null;
}

beforeEach(() => {
  fake = installFakeWebSocket();
});
afterEach(() => {
  fake.restore();
});

describe("WebSocketProvider", () => {
  it("opens a /ws/threads/<id>/ socket for thread.<id> channel", () => {
    const handler = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.42" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/threads/42/");
    expect(sock).toBeDefined();
    expect(sock?.url).toMatch(/\/ws\/threads\/42\/$/);
  });

  it("opens a /ws/notifications/ socket for the 'notifications' channel", () => {
    const handler = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="notifications" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/notifications/");
    expect(sock).toBeDefined();
    expect(sock?.url).toMatch(/\/ws\/notifications\/$/);
  });

  it("routes parsed JSON to the notifications handler via /ws/notifications/", () => {
    const handler = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="notifications" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/notifications/");
    expect(sock).toBeDefined();
    act(() => {
      sock!.emitMessage({ type: "notification.event", payload: { kind: "observer_done", title: "T" } });
    });
    expect(handler).toHaveBeenCalledWith({
      type: "notification.event",
      payload: { kind: "observer_done", title: "T" },
    });
  });

  it("opens a /ws/snapshots/<id>/ socket for snapshot.<id> channel", () => {
    const handler = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="snapshot.7" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/snapshots/7/");
    expect(sock).toBeDefined();
    expect(sock?.url).toMatch(/\/ws\/snapshots\/7\/$/);
  });

  it("throws 'Unknown channel:' for an unrecognized prefix", () => {
    // React will swallow the error in an error boundary in the render pipeline.
    // We suppress the console.error noise and catch the thrown error via try/catch
    // around act(), which re-throws render errors synchronously.
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      expect(() =>
        render(
          <WebSocketProvider>
            <TestConsumer channel="unknown.99" onMsg={vi.fn()} />
          </WebSocketProvider>,
        ),
      ).toThrow(/Unknown channel/);
    } catch {
      // If React's error boundary swallows it from render(), fall back to act():
      let thrown: Error | undefined;
      try {
        act(() => {
          render(
            <WebSocketProvider>
              <TestConsumer channel="unknown.99" onMsg={vi.fn()} />
            </WebSocketProvider>,
          );
        });
      } catch (e) {
        thrown = e as Error;
      }
      expect(thrown?.message).toMatch(/Unknown channel/);
    } finally {
      consoleSpy.mockRestore();
    }
  });

  it("routes parsed JSON to the channel's handler", () => {
    const handler = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/threads/1/");
    expect(sock).toBeDefined();
    act(() => {
      sock!.emitMessage({ type: "tok", text: "hi" });
    });
    expect(handler).toHaveBeenCalledWith({ type: "tok", text: "hi" });
  });

  it("does NOT deliver thread.1 messages to thread.2 subscribers", () => {
    const handler1 = vi.fn();
    const handler2 = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={handler1} />
        <TestConsumer channel="thread.2" onMsg={handler2} />
      </WebSocketProvider>,
    );
    const sock1 = fake.find("/ws/threads/1/");
    expect(sock1).toBeDefined();
    act(() => {
      sock1!.emitMessage({ type: "tok", text: "only-for-1" });
    });
    expect(handler1).toHaveBeenCalledWith({ type: "tok", text: "only-for-1" });
    expect(handler2).not.toHaveBeenCalled();
  });

  it("silently ignores malformed (non-JSON) payloads", () => {
    const handler = vi.fn();
    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/threads/1/");
    expect(sock).toBeDefined();
    // Emit raw non-JSON string directly via the socket's message listeners
    expect(() => {
      act(() => {
        (sock!.listeners.message ?? []).forEach((l) =>
          l(new MessageEvent("message", { data: "not json" })),
        );
      });
    }).not.toThrow();
    expect(handler).not.toHaveBeenCalled();
  });

  it("closes an open socket when the last subscriber unsubscribes (provider unmounts)", () => {
    const handler = vi.fn();
    const { unmount } = render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/threads/1/");
    expect(sock).toBeDefined();
    act(() => sock!.emitOpen());
    const closeSpy = vi.spyOn(sock!, "close");
    act(() => {
      unmount();
    });
    expect(closeSpy).toHaveBeenCalled();
  });

  it("defers closing a still-connecting socket until it opens (no mid-handshake abort)", () => {
    const handler = vi.fn();
    const { unmount } = render(
      <WebSocketProvider>
        <TestConsumer channel="thread.9" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/threads/9/");
    expect(sock).toBeDefined();
    expect(sock!.readyState).toBe(0); // CONNECTING — never opened
    const closeSpy = vi.spyOn(sock!, "close");

    act(() => unmount()); // teardown while the handshake is still in flight

    // Must NOT close mid-handshake (that is what logs the browser warning)...
    expect(closeSpy).not.toHaveBeenCalled();
    // ...but once it finishes connecting, the deferred close fires cleanly.
    act(() => sock!.emitOpen());
    expect(closeSpy).toHaveBeenCalled();
  });

  it("reconnects after an unexpected close while subscribers remain", () => {
    vi.useFakeTimers();
    try {
      const handler = vi.fn();
      render(
        <WebSocketProvider>
          <TestConsumer channel="thread.1" onMsg={handler} />
        </WebSocketProvider>,
      );
      const first = fake.find("/ws/threads/1/");
      expect(first).toBeDefined();
      act(() => first!.emitOpen());

      // Simulate an unexpected drop (e.g. the `web` container restarting in dev).
      act(() => first!.emitClose(1006));
      // Backoff timer fires -> a fresh socket for the same channel is opened.
      act(() => void vi.runOnlyPendingTimers());

      const all = fake.sockets.filter((s) => s.url.endsWith("/ws/threads/1/"));
      expect(all.length).toBe(2);

      // The replacement socket delivers to the still-registered handler.
      const second = all[all.length - 1];
      act(() => {
        second.emitOpen();
        second.emitMessage({ type: "tok", text: "after-reconnect" });
      });
      expect(handler).toHaveBeenCalledWith({ type: "tok", text: "after-reconnect" });
    } finally {
      vi.useRealTimers();
    }
  });

  it("does NOT reconnect after an intentional close (last subscriber leaves)", () => {
    vi.useFakeTimers();
    try {
      const handler = vi.fn();
      const { unmount } = render(
        <WebSocketProvider>
          <TestConsumer channel="thread.5" onMsg={handler} />
        </WebSocketProvider>,
      );
      expect(fake.sockets.filter((s) => s.url.endsWith("/ws/threads/5/")).length).toBe(1);
      act(() => unmount());
      act(() => void vi.runAllTimers());
      // No replacement socket: a deliberate teardown must not trigger a reconnect.
      expect(fake.sockets.filter((s) => s.url.endsWith("/ws/threads/5/")).length).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it("useWebSocket() throws outside provider", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      expect(() => render(<BadComponent />)).toThrow(
        /useWebSocket must be used inside WebSocketProvider/,
      );
    } finally {
      consoleSpy.mockRestore();
    }
  });

  it("sends ?since=<lastSeq> on reconnect to replay events missed during the gap", () => {
    vi.useFakeTimers();
    try {
      render(
        <WebSocketProvider>
          <TestConsumer channel="thread.1" onMsg={vi.fn()} />
        </WebSocketProvider>,
      );
      const first = fake.find("/ws/threads/1/");
      expect(first).toBeDefined();
      // First connect carries no ?since=.
      expect(first!.url).toMatch(/\/ws\/threads\/1\/$/);
      act(() => first!.emitOpen());
      // Server thread events carry a monotonic seq.
      act(() => {
        first!.emitMessage({ type: "tok", text: "a", seq: 3 });
        first!.emitMessage({ type: "tok", text: "b", seq: 7 });
      });
      // Unexpected drop -> backoff -> reconnect.
      act(() => first!.emitClose(1006));
      act(() => void vi.runOnlyPendingTimers());
      const all = fake.sockets.filter((s) => s.url.includes("/ws/threads/1/"));
      expect(all.length).toBe(2);
      // The replacement asks the server to replay everything after the last seq.
      expect(all[all.length - 1].url).toMatch(/\/ws\/threads\/1\/\?since=7$/);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not send ?since= for channels whose events carry no seq (notifications)", () => {
    vi.useFakeTimers();
    try {
      render(
        <WebSocketProvider>
          <TestConsumer channel="notifications" onMsg={vi.fn()} />
        </WebSocketProvider>,
      );
      const first = fake.find("/ws/notifications/");
      act(() => first!.emitOpen());
      act(() => first!.emitMessage({ type: "notification.event", payload: {} })); // no seq
      act(() => first!.emitClose(1006));
      act(() => void vi.runOnlyPendingTimers());
      const all = fake.sockets.filter((s) => s.url.includes("/ws/notifications/"));
      expect(all[all.length - 1].url).toMatch(/\/ws\/notifications\/$/);
    } finally {
      vi.useRealTimers();
    }
  });

  it("resets the replay cursor on deliberate teardown (re-subscribe is a fresh first-connect)", () => {
    const { unmount } = render(
      <WebSocketProvider>
        <TestConsumer channel="thread.3" onMsg={vi.fn()} />
      </WebSocketProvider>,
    );
    const first = fake.find("/ws/threads/3/");
    act(() => first!.emitOpen());
    act(() => first!.emitMessage({ type: "tok", text: "x", seq: 9 }));
    act(() => unmount()); // clears the per-channel replay cursor

    render(
      <WebSocketProvider>
        <TestConsumer channel="thread.3" onMsg={vi.fn()} />
      </WebSocketProvider>,
    );
    const fresh = fake.sockets.filter((s) => s.url.includes("/ws/threads/3/")).at(-1);
    expect(fresh!.url).toMatch(/\/ws\/threads\/3\/$/); // no stale ?since=9
  });
});
