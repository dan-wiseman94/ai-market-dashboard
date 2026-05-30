import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, vi } from "vitest";
import { installFakeWebSocket } from "./testUtils";
import { WebSocketProvider } from "@/realtime/WebSocketProvider";
import AppLayout from "@/components/layout/AppLayout";

function makeQc() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderWithProviders(router: ReturnType<typeof createMemoryRouter>) {
  return render(
    <QueryClientProvider client={makeQc()}>
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
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve({ results: [] }) }),
  ) as never;
  installFakeWebSocket();
});

test("g t navigates to /triggers", async () => {
  const user = userEvent.setup();
  renderWithProviders(makeRouter("/"));
  await user.keyboard("gt");
  expect(await screen.findByTestId("triggers")).toBeInTheDocument();
});

test("g c navigates to /costs", async () => {
  const user = userEvent.setup();
  renderWithProviders(makeRouter("/"));
  await user.keyboard("gc");
  expect(await screen.findByTestId("costs")).toBeInTheDocument();
});

test("shortcut ignored while typing in an input", async () => {
  const user = userEvent.setup();
  renderWithProviders(makeRouter("/snapshot"));
  const input = screen.getByTestId("snapshot").querySelector("input")!;
  input.focus();
  await user.keyboard("gt");
  expect(screen.getByTestId("snapshot")).toBeInTheDocument();
  expect(screen.queryByTestId("triggers")).not.toBeInTheDocument();
});

test("unmapped key after g cancels the binding", async () => {
  const user = userEvent.setup();
  renderWithProviders(makeRouter("/"));
  await user.keyboard("gx");
  expect(screen.getByTestId("dashboard")).toBeInTheDocument();
});

test("shortcut ignored on element with role=textbox", async () => {
  const user = userEvent.setup();
  renderWithProviders(makeRouter("/combobox"));
  (screen.getByTestId("role-textbox") as HTMLElement).focus();
  await user.keyboard("gt");
  expect(screen.getByTestId("combobox")).toBeInTheDocument();
  expect(screen.queryByTestId("triggers")).not.toBeInTheDocument();
});

test("? opens the shortcut help dialog listing all bindings", async () => {
  const user = userEvent.setup();
  renderWithProviders(makeRouter("/"));
  await user.keyboard("?");
  const dialog = await screen.findByRole("dialog", { name: /keyboard shortcuts/i });
  expect(dialog).toHaveTextContent("g t");
  expect(dialog).toHaveTextContent("Triggers");
});
