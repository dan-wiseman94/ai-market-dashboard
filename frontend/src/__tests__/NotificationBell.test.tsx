import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, fireEvent, waitFor, act } from "@testing-library/react";
import NotificationBell from "../components/NotificationBell";
import {
  installFakeWebSocket,
  mockApi,
  newQueryClient,
  renderWithProviders,
  type FakeWebSocketController,
} from "./testUtils";

const NOTIFS = [
  { id: 1, kind: "observer_done", title: "Fired", body: "snap 42",
    link: "/threads/observer/1", meta: {}, read_at: null,
    created_at: "2026-04-17T09:35:00Z" },
  { id: 2, kind: "error", title: "Boom", body: "bad",
    link: "", meta: {}, read_at: "2026-04-17T08:00:00Z",
    created_at: "2026-04-17T08:00:00Z" },
];

// renderWithProviders mounts <Toasts /> whose region is also labeled
// "Notifications" — target the bell by role to disambiguate.
const bellButton = () => screen.getByRole("button", { name: /notifications/i });

let fake: FakeWebSocketController;

beforeEach(() => {
  mockApi({ "GET /api/observer/notifications/": NOTIFS });
  fake = installFakeWebSocket();
});

afterEach(() => {
  fake.restore();
});

describe("NotificationBell", () => {
  it("shows unread badge count", async () => {
    renderWithProviders(<NotificationBell />);
    await waitFor(() => expect(screen.getByText("1")).toBeInTheDocument());
  });

  it("opens dropdown on click and lists notifications", async () => {
    renderWithProviders(<NotificationBell />);
    await waitFor(() => expect(bellButton()).toBeInTheDocument());
    fireEvent.click(bellButton());
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

    renderWithProviders(<NotificationBell />);
    await waitFor(() => expect(bellButton()).toBeInTheDocument());
    fireEvent.click(bellButton());
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

    renderWithProviders(<NotificationBell />);
    await waitFor(() => expect(bellButton()).toBeInTheDocument());
    fireEvent.click(bellButton());
    expect(screen.queryByText(/desktop notification/i)).toBeNull();
  });

  it("invalidates notifications query on notification.event via shared WS broker", async () => {
    const client = newQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    renderWithProviders(<NotificationBell />, { client });

    await waitFor(() => expect(bellButton()).toBeInTheDocument());

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
