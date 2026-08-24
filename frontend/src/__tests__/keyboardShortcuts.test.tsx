import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import { beforeEach } from "vitest";
import { installFakeWebSocket, mockFetch, newQueryClient } from "./testUtils";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import AppLayout from "@/components/layout/AppLayout";

// AppLayout calls useMatches() (breadcrumbs), a data-router-only hook, so these
// tests need createMemoryRouter/RouterProvider; testUtils' renderWithProviders
// wraps in a plain MemoryRouter and cannot host a data router.
function renderLayoutRouter(router: ReturnType<typeof createMemoryRouter>) {
  return render(
    <QueryClientProvider client={newQueryClient()}>
      <WebSocketProvider>
        <RouterProvider router={router} />
      </WebSocketProvider>
    </QueryClientProvider>,
  );
}

function makeRouter(entry = "/") {
  return createMemoryRouter(
    [{ path: "/", element: <AppLayout />, children: [
      { index: true, element: <div data-testid="dashboard">d</div> },
      { path: "triggers", element: <div data-testid="triggers">t</div> },
      { path: "costs", element: <div data-testid="costs">c</div> },
      { path: "snapshot", element: <div data-testid="snapshot"><input /></div> },
      { path: "combobox", element: (
        <div data-testid="combobox">
          <div role="textbox" tabIndex={0} data-testid="role-textbox" />
        </div>
      ) },
    ]}],
    { initialEntries: [entry] },
  );
}

beforeEach(() => {
  localStorage.clear();
  // Notifications is a bare-array endpoint; everything else here reads {results}.
  mockFetch((url) => ({
    ok: true,
    json: () => Promise.resolve(url.includes("/api/observer/notifications/") ? [] : { results: [] }),
  }));
  installFakeWebSocket();
});

test("g t navigates to /triggers", async () => {
  const user = userEvent.setup();
  renderLayoutRouter(makeRouter("/"));
  await user.keyboard("gt");
  expect(await screen.findByTestId("triggers")).toBeInTheDocument();
});

test("g c navigates to /costs", async () => {
  const user = userEvent.setup();
  renderLayoutRouter(makeRouter("/"));
  await user.keyboard("gc");
  expect(await screen.findByTestId("costs")).toBeInTheDocument();
});

test("shortcut ignored while typing in an input", async () => {
  const user = userEvent.setup();
  renderLayoutRouter(makeRouter("/snapshot"));
  const input = screen.getByTestId("snapshot").querySelector("input")!;
  input.focus();
  await user.keyboard("gt");
  expect(screen.getByTestId("snapshot")).toBeInTheDocument();
  expect(screen.queryByTestId("triggers")).not.toBeInTheDocument();
});

test("unmapped key after g cancels the binding", async () => {
  const user = userEvent.setup();
  renderLayoutRouter(makeRouter("/"));
  await user.keyboard("gx");
  expect(screen.getByTestId("dashboard")).toBeInTheDocument();
});

test("shortcut ignored on element with role=textbox", async () => {
  const user = userEvent.setup();
  renderLayoutRouter(makeRouter("/combobox"));
  (screen.getByTestId("role-textbox") as HTMLElement).focus();
  await user.keyboard("gt");
  expect(screen.getByTestId("combobox")).toBeInTheDocument();
  expect(screen.queryByTestId("triggers")).not.toBeInTheDocument();
});

test("? opens the shortcut help dialog listing all bindings", async () => {
  const user = userEvent.setup();
  renderLayoutRouter(makeRouter("/"));
  await user.keyboard("?");
  const dialog = await screen.findByRole("dialog", { name: /keyboard shortcuts/i });
  expect(dialog).toHaveTextContent("g t");
  expect(dialog).toHaveTextContent("Triggers");
});
