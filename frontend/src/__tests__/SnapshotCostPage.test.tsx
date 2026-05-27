import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { vi, test, expect } from "vitest";
import SnapshotCostPage from "@/pages/SnapshotCostPage";

const ROWS = [
  { section: "quotes", payload_tokens: 700, cost_share_usd: "0.0700" },
  { section: "news", payload_tokens: 300, cost_share_usd: "0.0300" },
];

/** Mount the page at /costs/snapshot/7 with a caller-supplied fetch responder. */
function mount(responder: (url: string) => unknown) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    const res = responder(String(url));
    return res instanceof Response ? res : new Response(JSON.stringify(res));
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [{ path: "/costs/snapshot/:id", element: <SnapshotCostPage /> }],
    { initialEntries: ["/costs/snapshot/7"] },
  );
  render(<QueryClientProvider client={qc}><RouterProvider router={router} /></QueryClientProvider>);
}

function costsAndDiff(diff: (url: string) => unknown) {
  return (url: string) =>
    url.includes("/api/costs/snapshot/7") ? ROWS : diff(url);
}

test("renders token attribution rows", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    if (String(url).includes("/api/costs/snapshot/7")) {
      return new Response(JSON.stringify([
        { section: "quotes", payload_tokens: 700, cost_share_usd: "0.0700" },
        { section: "news", payload_tokens: 300, cost_share_usd: "0.0300" },
      ]));
    }
    return new Response("[]");
  });

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [{ path: "/costs/snapshot/:id", element: <SnapshotCostPage /> }],
    { initialEntries: ["/costs/snapshot/7"] },
  );
  render(<QueryClientProvider client={qc}><RouterProvider router={router} /></QueryClientProvider>);

  expect(await screen.findByText(/quotes/i)).toBeInTheDocument();
  expect(await screen.findByText("$0.0700")).toBeInTheDocument();
});

test("Show diff fetches the diff and renders the delta", async () => {
  mount(costsAndDiff((u) =>
    u.includes("/api/snapshots/7/diff/")
      ? { delta: "+ added a news section", prev_id: 6, curr_id: 7 }
      : {},
  ));
  await screen.findByText(/quotes/i);

  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(await screen.findByText(/\+ added a news section/)).toBeInTheDocument();
  // The toggle flips its label once the diff is shown.
  expect(screen.getByRole("button", { name: /hide/i })).toBeInTheDocument();
});

test("renders a (no changes) placeholder when the delta is empty", async () => {
  mount(costsAndDiff((u) =>
    u.includes("/api/snapshots/7/diff/") ? { delta: "", prev_id: 6, curr_id: 7 } : {},
  ));
  await screen.findByText(/quotes/i);

  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(await screen.findByText("(no changes)")).toBeInTheDocument();
});

test("surfaces the API error message when there is no prior snapshot", async () => {
  mount(costsAndDiff((u) =>
    u.includes("/api/snapshots/7/diff/")
      ? new Response(JSON.stringify({ code: "no_prior", message: "No prior snapshot to diff against" }), { status: 404 })
      : {},
  ));
  await screen.findByText(/quotes/i);

  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(await screen.findByText(/no prior snapshot to diff against/i)).toBeInTheDocument();
});

test("Hide collapses the diff section again", async () => {
  mount(costsAndDiff((u) =>
    u.includes("/api/snapshots/7/diff/") ? { delta: "+ x", prev_id: 6, curr_id: 7 } : {},
  ));
  await screen.findByText(/quotes/i);

  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  await screen.findByText(/\+ x/);
  await userEvent.click(screen.getByRole("button", { name: /hide/i }));

  expect(screen.queryByText(/\+ x/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /show diff/i })).toBeInTheDocument();
});
