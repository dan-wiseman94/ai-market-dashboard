import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, vi } from "vitest";
import AppLayout from "@/components/layout/AppLayout";

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

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [] }) }),
  ) as never;
  (globalThis as { WebSocket?: unknown }).WebSocket = vi.fn(() => ({
    onmessage: null, onerror: null, onopen: null, onclose: null, close: vi.fn(),
  }));
});

test("static crumb renders for a route", () => {
  const router = createMemoryRouter(
    [{
      path: "/", element: <AppLayout />, handle: { crumb: "Home" },
      children: [
        { path: "triggers", handle: { crumb: "Triggers" }, element: <div>t</div> },
      ],
    }],
    { initialEntries: ["/triggers"] },
  );
  renderWithProviders(router);
  const nav = screen.getByRole("navigation", { name: /breadcrumb/i });
  expect(nav).toHaveTextContent("Home");
  expect(nav).toHaveTextContent("Triggers");
});

test("function crumb receives route params", () => {
  const router = createMemoryRouter(
    [{
      path: "/", element: <AppLayout />, handle: { crumb: "Home" },
      children: [
        {
          path: "threads/:id",
          handle: { crumb: ({ params }: { params: { id?: string } }) => `Thread ${params.id}` },
          element: <div>t</div>,
        },
      ],
    }],
    { initialEntries: ["/threads/42"] },
  );
  renderWithProviders(router);
  expect(screen.getByRole("navigation", { name: /breadcrumb/i })).toHaveTextContent("Thread 42");
});
