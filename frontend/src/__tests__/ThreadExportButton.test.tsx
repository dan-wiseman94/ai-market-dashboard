import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi, test, expect } from "vitest";
import ThreadExportButton from "@/components/ThreadExportButton";

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <MemoryRouter><QueryClientProvider client={qc}>{ui}</QueryClientProvider></MemoryRouter>;
}

test("clicking button POSTs to per-thread export endpoint", async () => {
  const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ id: 7, status: "pending" }), { status: 202 }),
  );
  render(wrap(<ThreadExportButton threadId={42} />));
  await userEvent.click(screen.getByRole("button", { name: /export/i }));
  const called = spy.mock.calls.some(
    ([u, init]) => String(u).includes("/api/export/thread/42/") && (init as any)?.method === "POST",
  );
  expect(called).toBe(true);
});
