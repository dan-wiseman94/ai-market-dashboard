import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import NotificationBell from "../components/NotificationBell";
import { installFakeWebSocket, type FakeWebSocketController } from "./testUtils";

const NOTIFS = [
  { id: 1, kind: "observer_done", title: "Fired", body: "snap 42",
    link: "/threads/observer/1", meta: {}, read_at: null,
    created_at: "2026-04-17T09:35:00Z" },
  { id: 2, kind: "error", title: "Boom", body: "bad",
    link: "", meta: {}, read_at: "2026-04-17T08:00:00Z",
    created_at: "2026-04-17T08:00:00Z" },
];

let fake: FakeWebSocketController;

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ results: NOTIFS }) }),
  ) as never;
  fake = installFakeWebSocket();
});

afterEach(() => {
  fake.restore();
});

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

/** Minimal wrapper: QueryClient + WebSocketProvider + Router. */
function Wrapper({ client, children }: { client: QueryClient; children: React.ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <WebSocketProvider>
        <MemoryRouter>{children}</MemoryRouter>
      </WebSocketProvider>
    </QueryClientProvider>
  );
}

describe("NotificationBell", () => {
  it("shows unread badge count", async () => {
    const client = qc();
    render(
      <Wrapper client={client}>
        <NotificationBell />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  it("opens dropdown on click and lists notifications", async () => {
    const client = qc();
    render(
      <Wrapper client={client}>
        <NotificationBell />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.getByText("Fired")).toBeInTheDocument();
    expect(screen.getByText("Boom")).toBeInTheDocument();
  });

  it("shows OS permission banner when Notification.permission is default", async () => {
    Object.defineProperty(window, "Notification", {
      configurable: true,
      value: Object.assign(class { } as unknown as typeof Notification, {
        permission: "default",
        requestPermission: vi.fn(() => Promise.resolve("granted")),
      }),
    });

    const client = qc();
    render(
      <Wrapper client={client}>
        <NotificationBell />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.getByText(/desktop notification/i)).toBeInTheDocument();
  });

  it("hides OS permission banner when Notification.permission is granted", async () => {
    Object.defineProperty(window, "Notification", {
      configurable: true,
      value: Object.assign(class { } as unknown as typeof Notification, {
        permission: "granted",
        requestPermission: vi.fn(() => Promise.resolve("granted")),
      }),
    });

    const client = qc();
    render(
      <Wrapper client={client}>
        <NotificationBell />
      </Wrapper>,
    );
    await waitFor(() => expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.queryByText(/desktop notification/i)).toBeNull();
  });

  it("invalidates notifications query on notification.event via shared WS broker", async () => {
    const client = qc();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    render(
      <Wrapper client={client}>
        <NotificationBell />
      </Wrapper>,
    );

    await waitFor(() => expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument());

    // The shared WebSocketProvider opens the socket via addEventListener (not onmessage).
    // emitMessage() calls all registered "message" listeners on the FakeSocket.
    const sock = fake.find("/ws/notifications/");
    expect(sock).toBeDefined();

    act(() => {
      sock!.emitMessage({
        type: "notification.event",
        payload: { kind: "observer_done", title: "T", body: "B" },
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["notifications"] }),
    );
  });
});
