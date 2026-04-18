import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi, test, expect, beforeEach } from "vitest";
import BackupsPage from "@/pages/BackupsPage";
import { ToastProvider } from "@/hooks/useToast";

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    if (u.includes("/api/backups/") && method === "GET") {
      return new Response(JSON.stringify({
        results: [
          { id: 1, created_at: "2026-04-18T02:30:00Z", filename: "2026-04-18-023000.sql.gz",
            size_bytes: 123456, sha256: "a".repeat(64), kind: "scheduled", status: "ok", error: "" },
        ],
      }));
    }
    if (u.includes("/api/backups/run") && method === "POST") {
      return new Response(JSON.stringify({ queued: true }), { status: 202 });
    }
    return new Response("{}");
  });
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <MemoryRouter><QueryClientProvider client={qc}><ToastProvider>{ui}</ToastProvider></QueryClientProvider></MemoryRouter>;
}

test("renders list with filename and size", async () => {
  render(wrap(<BackupsPage />));
  expect(await screen.findByText(/2026-04-18-023000\.sql\.gz/)).toBeInTheDocument();
});

test("clicking Back up now POSTs to run endpoint", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  render(wrap(<BackupsPage />));
  await userEvent.click(await screen.findByRole("button", { name: /back up now/i }));
  const called = spy.mock.calls.some(
    ([u, init]) => String(u).includes("/api/backups/run") && (init as RequestInit | undefined)?.method === "POST",
  );
  expect(called).toBe(true);
});
