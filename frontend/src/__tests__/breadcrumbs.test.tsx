import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { beforeEach } from "vitest";
import { installFakeWebSocket, mockFetch, newQueryClient } from "./testUtils";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import AppLayout from "@/components/layout/AppLayout";

// Breadcrumbs read route `handle` via useMatches, which needs a data router —
// testUtils' renderWithProviders (plain MemoryRouter) can't supply one.
function renderLayout(router: ReturnType<typeof createMemoryRouter>) {
  return render(
    <QueryClientProvider client={newQueryClient()}>
      <WebSocketProvider>
        <RouterProvider router={router} />
      </WebSocketProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockFetch(() => ({ ok: true, json: () => Promise.resolve({ results: [] }) }));
  installFakeWebSocket();
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
  renderLayout(router);
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
  renderLayout(router);
  expect(screen.getByRole("navigation", { name: /breadcrumb/i })).toHaveTextContent("Thread 42");
});
