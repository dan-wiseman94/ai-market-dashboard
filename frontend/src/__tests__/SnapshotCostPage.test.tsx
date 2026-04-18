import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { vi, test, expect } from "vitest";
import SnapshotCostPage from "@/pages/SnapshotCostPage";

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
