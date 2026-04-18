import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi, test, expect, beforeEach } from "vitest";
import ExportPage from "@/pages/ExportPage";
import { ToastProvider } from "@/hooks/useToast";

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    if (u.includes("/api/export/") && method === "POST") {
      return new Response(JSON.stringify({ id: 10, status: "pending" }), { status: 202 });
    }
    if (u.includes("/api/export/") && method === "GET") {
      return new Response(JSON.stringify({
        results: [
          { id: 1, status: "done", filename: "x.zip", size_bytes: 1024, error: "",
            created_at: "2026-04-18T00:00:00Z" },
        ],
      }));
    }
    return new Response("{}");
  });
});

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <MemoryRouter><QueryClientProvider client={qc}><ToastProvider>{ui}</ToastProvider></QueryClientProvider></MemoryRouter>;
}

test("renders scope form + recent jobs list", async () => {
  render(wrap(<ExportPage />));
  expect(screen.getByRole("button", { name: /start export/i })).toBeInTheDocument();
  expect(await screen.findByText(/x\.zip/)).toBeInTheDocument();
});

test("clicking Start export POSTs scope", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  render(wrap(<ExportPage />));
  await userEvent.click(screen.getByRole("button", { name: /start export/i }));
  const called = spy.mock.calls.some(
    ([u, init]) => String(u).endsWith("/api/export/") && (init as RequestInit | undefined)?.method === "POST",
  );
  expect(called).toBe(true);
});

test("shows 1 GB warning banner when total exceeds threshold", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    if (String(url).includes("/api/export/")) {
      return new Response(JSON.stringify({
        results: [
          { id: 1, status: "done", size_bytes: 600 * 1024 * 1024, filename: "a.zip", error: "", created_at: "" },
          { id: 2, status: "done", size_bytes: 600 * 1024 * 1024, filename: "b.zip", error: "", created_at: "" },
        ],
      }));
    }
    return new Response("{}");
  });
  render(wrap(<ExportPage />));
  expect(await screen.findByText(/consider deleting/i)).toBeInTheDocument();
});
