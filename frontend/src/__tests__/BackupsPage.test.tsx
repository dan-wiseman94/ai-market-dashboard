import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect, beforeEach } from "vitest";
import BackupsPage from "@/pages/BackupsPage";
import { renderWithProviders } from "./testUtils";

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

test("renders list with filename and size", async () => {
  renderWithProviders(<BackupsPage />);
  expect(await screen.findByText(/2026-04-18-023000\.sql\.gz/)).toBeInTheDocument();
});

test("clicking Back up now POSTs to run endpoint", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  renderWithProviders(<BackupsPage />);
  await userEvent.click(await screen.findByRole("button", { name: /back up now/i }));
  const called = spy.mock.calls.some(
    ([u, init]) => String(u).includes("/api/backups/run") && (init as RequestInit | undefined)?.method === "POST",
  );
  expect(called).toBe(true);
});

test("Delete opens a confirmation dialog that Cancel dismisses without deleting", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  renderWithProviders(<BackupsPage />);
  await userEvent.click(await screen.findByRole("button", { name: /^delete$/i }));

  const dialog = screen.getByRole("dialog", { name: /confirm delete backup/i });
  expect(dialog).toBeInTheDocument();

  await userEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  const deleted = spy.mock.calls.some(
    ([u, init]) => (init as RequestInit | undefined)?.method === "DELETE" && String(u).includes("/api/backups/1/"),
  );
  expect(deleted).toBe(false);
});

test("confirming the dialog sends DELETE and toasts success", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  renderWithProviders(<BackupsPage />);
  await userEvent.click(await screen.findByRole("button", { name: /^delete$/i }));

  const dialog = screen.getByRole("dialog", { name: /confirm delete backup/i });
  await userEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));

  const deleted = spy.mock.calls.some(
    ([u, init]) => (init as RequestInit | undefined)?.method === "DELETE" && String(u).includes("/api/backups/1/"),
  );
  expect(deleted).toBe(true);
  expect(await screen.findByText(/backup deleted/i)).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("clicking the backdrop dismisses the dialog", async () => {
  renderWithProviders(<BackupsPage />);
  await userEvent.click(await screen.findByRole("button", { name: /^delete$/i }));
  const dialog = screen.getByRole("dialog", { name: /confirm delete backup/i });
  // The backdrop is the dialog element itself; the inner panel stops propagation.
  await userEvent.click(dialog);
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
