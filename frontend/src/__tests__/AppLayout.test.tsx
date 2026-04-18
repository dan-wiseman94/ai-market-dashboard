import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AppLayout from "@/components/layout/AppLayout";
import { beforeEach, vi } from "vitest";
import userEvent from "@testing-library/user-event";

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderWithProviders(router: ReturnType<typeof createMemoryRouter>) {
  return render(
    <QueryClientProvider client={makeQc()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

test("AppLayout renders Outlet children", () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [
      { index: true, element: <div>child-page</div> },
    ]}],
    { initialEntries: ["/"] },
  );
  renderWithProviders(router);
  expect(screen.getByText("child-page")).toBeInTheDocument();
});

test("TopNav renders primary route links", () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [{ index: true, element: <div>x</div> }] }],
    { initialEntries: ["/"] },
  );
  renderWithProviders(router);
  expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/");
  expect(screen.getByRole("link", { name: /snapshot/i })).toHaveAttribute("href", "/snapshot");
  expect(screen.getByRole("link", { name: /threads/i })).toHaveAttribute("href", "/threads");
  expect(screen.getByRole("link", { name: /triggers/i })).toHaveAttribute("href", "/triggers");
  expect(screen.getByRole("link", { name: /schedules/i })).toHaveAttribute("href", "/schedules");
  expect(screen.getByRole("link", { name: /costs/i })).toHaveAttribute("href", "/costs");
});

beforeEach(() => {
  localStorage.clear();
  // Stub network deps needed by NotificationBell (now mounted in TopNav)
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [] }) }),
  ) as never;
  (globalThis as { WebSocket?: unknown }).WebSocket = vi.fn(() => ({
    onmessage: null, onerror: null, onopen: null, onclose: null,
    close: vi.fn(),
  }));
});

test("NotificationBell present on arbitrary child route", () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [
      { path: "anything", element: <div>x</div> },
    ]}],
    { initialEntries: ["/anything"] },
  );
  renderWithProviders(router);
  expect(screen.getByTestId("notification-bell")).toBeInTheDocument();
});

test("SideNav toggles and persists collapsed state", async () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [{ index: true, element: <div>x</div> }] }],
    { initialEntries: ["/"] },
  );
  const { unmount } = renderWithProviders(router);
  const toggle = screen.getByRole("button", { name: /toggle sidebar/i });
  expect(screen.getByText("Trading")).toBeVisible();

  await userEvent.click(toggle);
  expect(localStorage.getItem("ai-dashboard.sidebar.collapsed")).toBe("1");
  expect(screen.queryByText("Trading")).not.toBeInTheDocument();

  unmount();
  renderWithProviders(router);
  expect(screen.queryByText("Trading")).not.toBeInTheDocument();
});
