import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import NotificationBell from "../components/NotificationBell";

const NOTIFS = [
  { id: 1, kind: "observer_done", title: "Fired", body: "snap 42",
    link: "/threads/observer/1", meta: {}, read_at: null,
    created_at: "2026-04-17T09:35:00Z" },
  { id: 2, kind: "error", title: "Boom", body: "bad",
    link: "", meta: {}, read_at: "2026-04-17T08:00:00Z",
    created_at: "2026-04-17T08:00:00Z" },
];

beforeEach(() => {
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ results: NOTIFS }) }),
  ) as never;
  // Stub WebSocket so the constructor inside the component doesn't actually open one.
  (global as { WebSocket?: unknown }).WebSocket = vi.fn(() => ({
    onmessage: null, onerror: null, onopen: null, onclose: null,
    close: vi.fn(),
  }));
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
});
