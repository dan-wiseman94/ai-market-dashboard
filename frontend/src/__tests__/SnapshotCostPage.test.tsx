import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { test, expect } from "vitest";
import { mockApi, renderWithProviders, type Route } from "./testUtils";
import SnapshotCostPage from "@/pages/SnapshotCostPage";

const ROWS = [
  { section: "quotes", payload_tokens: 700, cost_share_usd: "0.0700" },
  { section: "news", payload_tokens: 300, cost_share_usd: "0.0300" },
];

/** Mount the page at /costs/snapshot/7; extra routes cover the diff endpoint. */
function mount(extraRoutes: Record<Route, unknown> = {} as Record<Route, unknown>) {
  mockApi({ "GET /api/costs/snapshot/7": ROWS, ...extraRoutes });
  renderWithProviders(<SnapshotCostPage />, {
    routePath: "/costs/snapshot/:id",
    initialEntries: ["/costs/snapshot/7"],
  });
}

test("renders token attribution rows", async () => {
  mount();

  expect(await screen.findByText(/quotes/i)).toBeInTheDocument();
  expect(await screen.findByText("$0.0700")).toBeInTheDocument();
});

test("Show diff fetches the diff and renders the delta", async () => {
  mount({ "GET /api/snapshots/7/diff/": { delta: "+ added a news section", prev_id: 6, curr_id: 7 } });
  await screen.findByText(/quotes/i);

  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(await screen.findByText(/\+ added a news section/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /hide/i })).toBeInTheDocument();
});

test("renders a (no changes) placeholder when the delta is empty", async () => {
  mount({ "GET /api/snapshots/7/diff/": { delta: "", prev_id: 6, curr_id: 7 } });
  await screen.findByText(/quotes/i);

  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(await screen.findByText("(no changes)")).toBeInTheDocument();
});

test("surfaces the API error message when there is no prior snapshot", async () => {
  mount({
    "GET /api/snapshots/7/diff/": { status: 404, code: "no_prior", message: "No prior snapshot to diff against" },
  });
  await screen.findByText(/quotes/i);

  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  expect(await screen.findByText(/no prior snapshot to diff against/i)).toBeInTheDocument();
});

test("Hide collapses the diff section again", async () => {
  mount({ "GET /api/snapshots/7/diff/": { delta: "+ x", prev_id: 6, curr_id: 7 } });
  await screen.findByText(/quotes/i);

  await userEvent.click(screen.getByRole("button", { name: /show diff/i }));
  await screen.findByText(/\+ x/);
  await userEvent.click(screen.getByRole("button", { name: /hide/i }));

  expect(screen.queryByText(/\+ x/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /show diff/i })).toBeInTheDocument();
});
