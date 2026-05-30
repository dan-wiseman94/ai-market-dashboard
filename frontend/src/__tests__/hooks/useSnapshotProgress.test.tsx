/**
 * TDD tests for useSnapshotProgress hook.
 *
 * The hook subscribes to the snapshot.<id> WS channel and collects
 * {type:"snapshot.section", section: string, status: "running"|"done"|"failed"}
 * events into a Map<section, status> that the UI renders as a checklist.
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import { installFakeWebSocket, type FakeWebSocketController } from "../testUtils";
import { useSnapshotProgress } from "@/hooks/useSnapshotProgress";

let fake: FakeWebSocketController;

function wrapper({ children }: { children: React.ReactNode }) {
  return <WebSocketProvider>{children}</WebSocketProvider>;
}

beforeEach(() => {
  fake = installFakeWebSocket();
});
afterEach(() => {
  fake.restore();
});

describe("useSnapshotProgress", () => {
  it("returns an empty map when snapshotId is null", () => {
    const { result } = renderHook(() => useSnapshotProgress(null), { wrapper });
    expect(result.current.sections.size).toBe(0);
  });

  it("opens a snapshot WS channel when snapshotId is provided", () => {
    renderHook(() => useSnapshotProgress(42), { wrapper });
    const sock = fake.find("/ws/snapshots/42/");
    expect(sock).toBeDefined();
  });

  it("records 'running' status for a section on snapshot.section event", () => {
    const { result } = renderHook(() => useSnapshotProgress(7), { wrapper });
    const sock = fake.find("/ws/snapshots/7/");
    expect(sock).toBeDefined();

    act(() => {
      sock!.emitMessage({ type: "snapshot.section", section: "quotes", status: "running" });
    });

    expect(result.current.sections.get("quotes")).toBe("running");
  });

  it("updates to 'done' when a second event arrives for the same section", () => {
    const { result } = renderHook(() => useSnapshotProgress(7), { wrapper });
    const sock = fake.find("/ws/snapshots/7/");

    act(() => {
      sock!.emitMessage({ type: "snapshot.section", section: "quotes", status: "running" });
    });
    act(() => {
      sock!.emitMessage({ type: "snapshot.section", section: "quotes", status: "done" });
    });

    expect(result.current.sections.get("quotes")).toBe("done");
  });

  it("tracks multiple sections independently", () => {
    const { result } = renderHook(() => useSnapshotProgress(7), { wrapper });
    const sock = fake.find("/ws/snapshots/7/");

    act(() => {
      sock!.emitMessage({ type: "snapshot.section", section: "quotes", status: "done" });
      sock!.emitMessage({ type: "snapshot.section", section: "chain", status: "running" });
      sock!.emitMessage({ type: "snapshot.section", section: "news", status: "failed" });
    });

    expect(result.current.sections.get("quotes")).toBe("done");
    expect(result.current.sections.get("chain")).toBe("running");
    expect(result.current.sections.get("news")).toBe("failed");
    expect(result.current.sections.size).toBe(3);
  });

  it("ignores events with a different type", () => {
    const { result } = renderHook(() => useSnapshotProgress(7), { wrapper });
    const sock = fake.find("/ws/snapshots/7/");

    act(() => {
      sock!.emitMessage({ type: "something.else", section: "quotes", status: "done" });
    });

    expect(result.current.sections.size).toBe(0);
  });

  it("does not subscribe when snapshotId is null (no WS socket opened)", () => {
    renderHook(() => useSnapshotProgress(null), { wrapper });
    expect(fake.sockets.length).toBe(0);
  });
});
