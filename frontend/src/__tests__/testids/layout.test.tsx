import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { installFakeWebSocket, mockFetch, newQueryClient, renderWithProviders } from "../testUtils";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import Breadcrumbs from "../../components/layout/Breadcrumbs";
import ConnectionStatusDot from "../../components/layout/ConnectionStatusDot";
import NotificationBell from "../../components/NotificationBell";
import { CommandPalette } from "../../components/CommandPalette";
import { Skeleton } from "../../components/Skeleton";

beforeEach(() => {
  // Stub fetch so QueryClient / useHealth don't throw
  mockFetch(() => ({ ok: true, json: () => Promise.resolve({ results: [] }) }));
  // Stub WebSocket so NotificationBell doesn't open a real socket
  installFakeWebSocket();
});

describe("layout testids", () => {
  // Breadcrumbs returns null when useMatches yields no crumbs. Route handles
  // (handle.crumb) only exist in a data router, so this test must drive the
  // component through createMemoryRouter/RouterProvider — renderWithProviders'
  // plain MemoryRouter cannot attach handles.
  it("Breadcrumbs root has data-testid='breadcrumb-trail'", () => {
    const router = createMemoryRouter(
      [
        {
          path: "/",
          handle: { crumb: "Home" },
          element: (
            <QueryClientProvider client={newQueryClient()}>
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
    renderWithProviders(<ConnectionStatusDot />);
    expect(screen.getByTestId("connection-status-dot")).toBeInTheDocument();
  });

  it("NotificationBell has data-testid='notification-bell'", () => {
    renderWithProviders(<NotificationBell />);
    expect(screen.getByTestId("notification-bell")).toBeInTheDocument();
  });

  it("CommandPalette has data-testid='command-palette' when open", () => {
    renderWithProviders(<CommandPalette open onClose={() => {}} commands={[]} />);
    expect(screen.getByTestId("command-palette")).toBeInTheDocument();
  });

  it("CommandPalette is absent from DOM when closed", () => {
    renderWithProviders(<CommandPalette open={false} onClose={() => {}} commands={[]} />);
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
