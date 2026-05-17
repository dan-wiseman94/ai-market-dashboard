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

  it("closes the socket when the last subscriber unsubscribes (provider unmounts)", () => {
    const handler = vi.fn();
    const { unmount } = render(
      <WebSocketProvider>
        <TestConsumer channel="thread.1" onMsg={handler} />
      </WebSocketProvider>,
    );
    const sock = fake.find("/ws/threads/1/");
    expect(sock).toBeDefined();
    const closeSpy = vi.spyOn(sock!, "close");
    act(() => {
      unmount();
    });
    expect(closeSpy).toHaveBeenCalled();
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
});
