import { renderHook, act } from "@testing-library/react";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import AppLayout from "@/components/layout/AppLayout";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import { installFakeWebSocket, mockFetch, newQueryClient } from "./testUtils";

describe("useDocumentTitle", () => {
  const original = document.title;

  afterEach(() => {
    document.title = original;
  });

  it("sets document.title to '<title> · Ledger'", () => {
    const { unmount } = renderHook(() => useDocumentTitle("Dashboard"));
    expect(document.title).toBe("Dashboard · Ledger");
    unmount();
  });

  it("restores the previous title on unmount", () => {
    document.title = "Previous Title";
    const { unmount } = renderHook(() => useDocumentTitle("New Page"));
    expect(document.title).toBe("New Page · Ledger");
    unmount();
    expect(document.title).toBe("Previous Title");
  });

  it("does nothing when title is undefined", () => {
    document.title = "Untouched";
    renderHook(() => useDocumentTitle(undefined));
    expect(document.title).toBe("Untouched");
  });

  it("updates when title changes", () => {
    let title = "First";
    const { rerender } = renderHook(() => useDocumentTitle(title));
    expect(document.title).toBe("First · Ledger");
    act(() => {
      title = "Second";
    });
    rerender();
    expect(document.title).toBe("Second · Ledger");
  });
});

// These tests hand-roll createMemoryRouter/RouterProvider (not
// renderWithProviders) because route `handle`s — the crumb source under test —
// only exist in a data router, which a plain MemoryRouter cannot express.
describe("AppLayout document.title wiring", () => {
  const original = document.title;

  beforeEach(() => {
    mockFetch(() => ({ ok: true, json: () => Promise.resolve({ results: [] }) }));
    installFakeWebSocket();
  });

  afterEach(() => {
    document.title = original;
  });

  it("sets the tab title from the leaf route crumb", () => {
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: <AppLayout />,
          handle: { crumb: "Home" },
          children: [
            {
              path: "schedules",
              element: <div>schedules page</div>,
              handle: { crumb: "Schedules" },
            },
          ],
        },
      ],
      { initialEntries: ["/schedules"] },
    );

    render(
      <QueryClientProvider client={newQueryClient()}>
        <WebSocketProvider>
          <RouterProvider router={router} />
        </WebSocketProvider>
      </QueryClientProvider>,
    );

    expect(screen.getByText("schedules page")).toBeInTheDocument();
    expect(document.title).toBe("Schedules · Ledger");
  });

  it("sets title from a crumb function (params interpolation)", () => {
    const router = createMemoryRouter(
      [
        {
          path: "/",
          element: <AppLayout />,
          handle: { crumb: "Home" },
          children: [
            {
              path: "threads/:id",
              element: <div>thread page</div>,
              handle: {
                crumb: ({ params }: { params: { id?: string } }) =>
                  `Thread ${params.id}`,
              },
            },
          ],
        },
      ],
      { initialEntries: ["/threads/42"] },
    );

    render(
      <QueryClientProvider client={newQueryClient()}>
        <WebSocketProvider>
          <RouterProvider router={router} />
        </WebSocketProvider>
      </QueryClientProvider>,
    );

    expect(document.title).toBe("Thread 42 · Ledger");
  });
});
