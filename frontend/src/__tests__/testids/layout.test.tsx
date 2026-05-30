import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { installFakeWebSocket } from "../testUtils";
import { MemoryRouter, createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import Breadcrumbs from "../../components/layout/Breadcrumbs";
import ConnectionStatusDot from "../../components/layout/ConnectionStatusDot";
import NotificationBell from "../../components/NotificationBell";
import { CommandPalette } from "../../components/CommandPalette";
import { Skeleton } from "../../components/Skeleton";

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(() => {
  // Stub fetch so QueryClient / useHealth don't throw
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [] }) }),
  ) as never;
  // Stub WebSocket so NotificationBell doesn't open a real socket
  installFakeWebSocket();
});

describe("layout testids", () => {
  // Breadcrumbs returns null when useMatches yields no crumbs, so we need a
  // router with at least one route that has a handle.crumb to force a render.
  // MemoryRouter alone doesn't expose useMatches with handles, so we render a
  // static crumb by wrapping the component inside a MemoryRouter with an
  // explicit initialEntries and testing via the nav role it already renders.
  // However, to keep the test minimal we just verify the testid is present
  // when the component does render.  We achieve this by driving it through
  // createMemoryRouter so we can attach handles.
  it("Breadcrumbs root has data-testid='breadcrumb-trail'", () => {
    const router = createMemoryRouter(
      [
        {
          path: "/",
          handle: { crumb: "Home" },
          element: (
            <QueryClientProvider client={makeQc()}>
              <Breadcrumbs />
            </QueryClientProvider>
          ),
        },
      ],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    expect(screen.getByTestId("breadcrumb-trail")).toBeInTheDocument();
  });

  it("ConnectionStatusDot has data-testid='connection-status-dot'", () => {
    render(
      <QueryClientProvider client={makeQc()}>
        <ConnectionStatusDot />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("connection-status-dot")).toBeInTheDocument();
  });

  it("NotificationBell has data-testid='notification-bell'", () => {
    render(
      <QueryClientProvider client={makeQc()}>
        <WebSocketProvider>
          <MemoryRouter>
            <NotificationBell />
          </MemoryRouter>
        </WebSocketProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("notification-bell")).toBeInTheDocument();
  });

  it("CommandPalette has data-testid='command-palette' when open", () => {
    render(
      <MemoryRouter>
        <CommandPalette open onClose={() => {}} commands={[]} />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("command-palette")).toBeInTheDocument();
  });

  it("CommandPalette is absent from DOM when closed", () => {
    render(
      <MemoryRouter>
        <CommandPalette open={false} onClose={() => {}} commands={[]} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("command-palette")).not.toBeInTheDocument();
  });

  it("Skeleton has data-testid='skeleton-generic' by default", () => {
    render(<Skeleton />);
    expect(screen.getByTestId("skeleton-generic")).toBeInTheDocument();
  });

  it("Skeleton accepts a `where` prop and uses it in testid", () => {
    render(<Skeleton where="dashboard" />);
    expect(screen.getByTestId("skeleton-dashboard")).toBeInTheDocument();
  });
});
