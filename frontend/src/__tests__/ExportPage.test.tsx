import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect, beforeEach } from "vitest";
import ExportPage from "@/pages/ExportPage";
import { renderWithProviders } from "./testUtils";

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

test("renders scope form + recent jobs list", async () => {
  renderWithProviders(<ExportPage />);
  expect(screen.getByRole("button", { name: /start export/i })).toBeInTheDocument();
  expect(await screen.findByText(/x\.zip/)).toBeInTheDocument();
});

test("clicking Start export POSTs scope", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  renderWithProviders(<ExportPage />);
  await userEvent.click(screen.getByRole("button", { name: /start export/i }));
  const called = spy.mock.calls.some(
    ([u, init]) => String(u).endsWith("/api/export/") && (init as RequestInit | undefined)?.method === "POST",
  );
  expect(called).toBe(true);
});

test("unchecking every scope sends the minimal scope", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  renderWithProviders(<ExportPage />);
  for (const name of [/threads/i, /snapshots/i, /observations/i, /triggers/i, /profiles/i]) {
    await userEvent.click(screen.getByRole("checkbox", { name }));
  }
  await userEvent.click(screen.getByRole("button", { name: /start export/i }));

  const posts = spy.mock.calls.filter(
    ([u, init]) => String(u).endsWith("/api/export/") && (init as RequestInit | undefined)?.method === "POST",
  );
  const { scope } = JSON.parse((posts.at(-1)![1] as RequestInit).body as string);
  expect(scope).toMatchObject({ observations: false, triggers: false, profiles: false, watchlists: false });
  // "all" scopes become undefined and drop out of the JSON entirely.
  expect(scope.threads).toBeUndefined();
  expect(scope.snapshots).toBeUndefined();
});

test("toasts an error when starting an export fails", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.includes("/api/export/") && (init?.method ?? "GET").toUpperCase() === "POST") {
      return new Response(JSON.stringify({ code: "boom", message: "disk full" }), { status: 500 });
    }
    if (u.includes("/api/export/")) return new Response(JSON.stringify({ results: [] }));
    return new Response("{}");
  });
  renderWithProviders(<ExportPage />);
  await userEvent.click(screen.getByRole("button", { name: /start export/i }));
  expect(await screen.findByText(/disk full/i)).toBeInTheDocument();
});

test("Delete on a finished job sends DELETE for that job", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  renderWithProviders(<ExportPage />);
  await screen.findByText(/x\.zip/);
  await userEvent.click(screen.getByRole("button", { name: /delete/i }));
  const deleted = spy.mock.calls.some(
    ([u, init]) => String(u).endsWith("/api/export/1/") && (init as RequestInit | undefined)?.method === "DELETE",
  );
  expect(deleted).toBe(true);
});

test("toggling a scope checkbox changes what gets POSTed", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  renderWithProviders(<ExportPage />);
  // Observations defaults to checked; turn it off before starting the export.
  await userEvent.click(screen.getByRole("checkbox", { name: /observations/i }));
  await userEvent.click(screen.getByRole("button", { name: /start export/i }));

  // mock.calls accumulates across tests in this file; take the POST we just made.
  const posts = spy.mock.calls.filter(
    ([u, init]) => String(u).endsWith("/api/export/") && (init as RequestInit | undefined)?.method === "POST",
  );
  const body = JSON.parse((posts.at(-1)![1] as RequestInit).body as string);
  expect(body.scope.observations).toBe(false);
  // Untouched scopes are still present.
  expect(body.scope.triggers).toBe(true);
});

test("Retry on a failed job re-POSTs that job's scope", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const u = String(url);
    if (u.includes("/api/export/") && (init?.method ?? "GET").toUpperCase() === "POST") {
      return new Response(JSON.stringify({ id: 11, status: "pending" }), { status: 202 });
    }
    if (u.includes("/api/export/")) {
      return new Response(JSON.stringify({
        results: [
          { id: 2, status: "failed", filename: "", size_bytes: null, error: "boom",
            created_at: "2026-04-18T00:00:00Z", scope: { threads: "all", triggers: false } },
        ],
      }));
    }
    return new Response("{}");
  });
  const spy = vi.spyOn(globalThis, "fetch");
  renderWithProviders(<ExportPage />);
  await userEvent.click(await screen.findByRole("button", { name: /retry/i }));

  const posts = spy.mock.calls.filter(
    ([u, init]) => String(u).endsWith("/api/export/") && (init as RequestInit | undefined)?.method === "POST",
  );
  const body = JSON.parse((posts.at(-1)![1] as RequestInit).body as string);
  expect(body.scope).toEqual({ threads: "all", triggers: false });
});

test("Start export is disabled while a job is still running", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    if (String(url).includes("/api/export/")) {
      return new Response(JSON.stringify({
        results: [
          { id: 3, status: "running", filename: "", size_bytes: null, error: "",
            created_at: "2026-04-18T00:00:00Z" },
        ],
      }));
    }
    return new Response("{}");
  });
  renderWithProviders(<ExportPage />);
  await screen.findByText(/running…/i);
  expect(screen.getByRole("button", { name: /start export/i })).toBeDisabled();
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
  renderWithProviders(<ExportPage />);
  expect(await screen.findByText(/consider deleting/i)).toBeInTheDocument();
});
