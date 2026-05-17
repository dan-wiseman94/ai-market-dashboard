import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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

describe("NotificationBell", () => {
  it("shows unread badge count", async () => {
    render(
      <QueryClientProvider client={qc()}>
        <MemoryRouter><NotificationBell /></MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  it("opens dropdown on click and lists notifications", async () => {
    render(
      <QueryClientProvider client={qc()}>
        <MemoryRouter><NotificationBell /></MemoryRouter>
      </QueryClientProvider>,
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

    render(
      <QueryClientProvider client={qc()}>
        <MemoryRouter><NotificationBell /></MemoryRouter>
      </QueryClientProvider>,
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

    render(
      <QueryClientProvider client={qc()}>
        <MemoryRouter><NotificationBell /></MemoryRouter>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText(/notifications/i));
    expect(screen.queryByText(/desktop notification/i)).toBeNull();
  });

  it("invalidates notifications query on notification.event WebSocket message", async () => {
    const client = qc();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter><NotificationBell /></MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByLabelText(/notifications/i)).toBeInTheDocument());

    // NotificationBell uses ws.onmessage (property) not addEventListener,
    // so we retrieve the FakeSocket and call onmessage directly.
    const sock = fake.find("/ws/notifications/");
    expect(sock).toBeDefined();

    const onmessageFn = (sock as unknown as { onmessage: ((ev: MessageEvent) => void) | null }).onmessage;
    if (onmessageFn) {
      act(() => {
        onmessageFn(
          new MessageEvent("message", {
            data: JSON.stringify({ type: "notification.event", payload: { kind: "observer_done", title: "T", body: "B" } }),
          }),
        );
      });
      expect(invalidateSpy).toHaveBeenCalledWith(expect.objectContaining({ queryKey: ["notifications"] }));
    }
  });
});
