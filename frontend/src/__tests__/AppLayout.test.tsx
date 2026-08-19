import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import AppLayout from "@/components/layout/AppLayout";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import { beforeEach } from "vitest";
import { installFakeWebSocket, mockFetch, newQueryClient } from "./testUtils";
import userEvent from "@testing-library/user-event";

// AppLayout needs a data router (Outlet children + useMatches breadcrumbs), so
// testUtils' renderWithProviders (plain MemoryRouter) can't host it — a
// RouterProvider nested inside another Router throws.
function renderLayout(router: ReturnType<typeof createMemoryRouter>) {
  return render(
    <QueryClientProvider client={newQueryClient()}>
      <WebSocketProvider>
        <RouterProvider router={router} />
      </WebSocketProvider>
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
  renderLayout(router);
  expect(screen.getByText("child-page")).toBeInTheDocument();
});

test("TopNav renders primary route links", () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [{ index: true, element: <div>x</div> }] }],
    { initialEntries: ["/"] },
  );
  renderLayout(router);
  expect(screen.getByRole("link", { name: /dashboard/i })).toHaveAttribute("href", "/");
  // Exact match: the SideNav now also has a "Snapshots" browser link (/snapshots),
  // so /snapshot/i would match two elements. The TopNav composer link is exactly "Snapshot".
  expect(screen.getByRole("link", { name: "Snapshot" })).toHaveAttribute("href", "/snapshot");
  expect(screen.getByRole("link", { name: /threads/i })).toHaveAttribute("href", "/threads");
  expect(screen.getByRole("link", { name: /triggers/i })).toHaveAttribute("href", "/triggers");
  expect(screen.getByRole("link", { name: /schedules/i })).toHaveAttribute("href", "/schedules");
  expect(screen.getByRole("link", { name: /costs/i })).toHaveAttribute("href", "/costs");
});

beforeEach(() => {
  localStorage.clear();
  // Stub network deps needed by NotificationBell (now mounted in TopNav)
  mockFetch(() => ({ ok: true, json: () => Promise.resolve({ results: [] }) }));
  installFakeWebSocket();
});

test("NotificationBell present on arbitrary child route", () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [
      { path: "anything", element: <div>x</div> },
    ]}],
    { initialEntries: ["/anything"] },
  );
  renderLayout(router);
  expect(screen.getByTestId("notification-bell")).toBeInTheDocument();
});

test("SideNav toggles and persists collapsed state", async () => {
  const router = createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [{ index: true, element: <div>x</div> }] }],
    { initialEntries: ["/"] },
  );
  const { unmount } = renderLayout(router);
  const toggle = screen.getByRole("button", { name: /toggle sidebar/i });
  expect(screen.getByText("Trading")).toBeVisible();

  await userEvent.click(toggle);
  expect(localStorage.getItem("ai-dashboard.sidebar.collapsed")).toBe("1");
  expect(screen.queryByText("Trading")).not.toBeInTheDocument();

  unmount();
  renderLayout(router);
  expect(screen.queryByText("Trading")).not.toBeInTheDocument();
});
