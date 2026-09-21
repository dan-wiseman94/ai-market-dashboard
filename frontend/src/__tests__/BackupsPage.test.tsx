import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect, beforeEach } from "vitest";
import BackupsPage from "@/pages/BackupsPage";
import { renderWithProviders } from "./testUtils";

const FILENAME = "2026-04-18-023000.sql.gz";

// Per-test override for POST /api/backups/{id}/restore/. Default: a clean restore.
let restoreResponder: (body: unknown) => Promise<Response> = async () =>
  new Response(
    JSON.stringify({
      restored: true,
      backup_id: 1,
      filename: FILENAME,
      duration_ms: 5120,
      workers_quiesced: false,
      warning: "worker and beat kept running through the restore — restart them.",
    }),
  );

function errorResponse(status: number, body: Record<string, unknown>) {
  return new Response(JSON.stringify(body), { status });
}

beforeEach(() => {
  restoreResponder = async () =>
    new Response(
      JSON.stringify({
        restored: true,
        backup_id: 1,
        filename: FILENAME,
        duration_ms: 5120,
        workers_quiesced: false,
        warning: "worker and beat kept running through the restore — restart them.",
      }),
    );
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url, init) => {
    const u = String(url);
    const method = (init?.method ?? "GET").toUpperCase();
    if (u.includes("/api/backups/") && method === "GET") {
      return new Response(JSON.stringify({
        results: [
          { id: 1, created_at: "2026-04-18T02:30:00Z", filename: FILENAME,
            size_bytes: 123456, sha256: "a".repeat(64), kind: "scheduled", status: "ok", error: "" },
        ],
      }));
    }
    if (u.includes("/restore/") && method === "POST") {
      const raw = init?.body;
      return restoreResponder(typeof raw === "string" ? JSON.parse(raw) : raw);
    }
    if (u.includes("/api/backups/run") && method === "POST") {
      return new Response(JSON.stringify({ queued: true }), { status: 202 });
    }
    return new Response("{}");
  });
});

test("renders list with filename and size", async () => {
  renderWithProviders(<BackupsPage />);
  expect(await screen.findByText(FILENAME)).toBeInTheDocument();
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

test("every backup row exposes download, restore and delete", async () => {
  renderWithProviders(<BackupsPage />);
  const row = await screen.findByTestId("backup-row-1");
  expect(within(row).getByRole("link", { name: /download/i })).toHaveAttribute(
    "href",
    "/api/backups/1/download/",
  );
  expect(within(row).getByRole("button", { name: /^restore$/i })).toBeEnabled();
  expect(within(row).getByRole("button", { name: /^delete$/i })).toBeEnabled();
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

/* ── Restore ─────────────────────────────────────────────────────────────── */

async function openRestoreDialog() {
  renderWithProviders(<BackupsPage />);
  await userEvent.click(await screen.findByRole("button", { name: /^restore$/i }));
  return screen.getByRole("dialog", { name: /restore the database from this backup/i });
}

function restoreButton(dialog: HTMLElement) {
  return within(dialog).getByRole("button", { name: /^restor(e|ing)/i });
}

test("the restore button stays disabled until the filename is typed exactly", async () => {
  const dialog = await openRestoreDialog();
  expect(restoreButton(dialog)).toBeDisabled();

  const input = within(dialog).getByLabelText(/backup filename/i);
  await userEvent.type(input, FILENAME.slice(0, -3));
  expect(restoreButton(dialog)).toBeDisabled();

  await userEvent.clear(input);
  await userEvent.type(input, FILENAME.toUpperCase());
  expect(restoreButton(dialog)).toBeDisabled();

  await userEvent.clear(input);
  await userEvent.type(input, FILENAME);
  expect(restoreButton(dialog)).toBeEnabled();
});

test("a confirmed restore POSTs the filename and reports success", async () => {
  const spy = vi.spyOn(globalThis, "fetch");
  const dialog = await openRestoreDialog();
  await userEvent.type(within(dialog).getByLabelText(/backup filename/i), FILENAME);
  await userEvent.click(restoreButton(dialog));

  const call = spy.mock.calls.find(
    ([u, init]) => String(u).includes("/api/backups/1/restore/") &&
      (init as RequestInit | undefined)?.method === "POST",
  );
  expect(call).toBeDefined();
  expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ confirm: FILENAME });

  expect(await screen.findByText(/restored from/i)).toBeInTheDocument();
  expect(screen.getByText(/5\.1s/)).toBeInTheDocument();
  // The dialog closes and the worker caveat from the response is surfaced.
  expect(screen.queryByRole("dialog", { name: /restore the database/i })).not.toBeInTheDocument();
  expect(screen.getByText(/restart them/i)).toBeInTheDocument();
  expect(await screen.findByText(/every view now shows restored data/i)).toBeInTheDocument();
});

test("the page is locked while the restore is in flight", async () => {
  let release: (r: Response) => void = () => {};
  restoreResponder = () => new Promise<Response>((resolve) => { release = resolve; });

  const dialog = await openRestoreDialog();
  await userEvent.type(within(dialog).getByLabelText(/backup filename/i), FILENAME);
  await userEvent.click(restoreButton(dialog));

  expect(await within(dialog).findByText(/restoring the database from/i)).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: /cancel/i })).toBeDisabled();
  expect(screen.getByRole("button", { name: /back up now/i })).toBeDisabled();
  const row = screen.getByTestId("backup-row-1");
  expect(within(row).getByRole("button", { name: /^delete$/i })).toBeDisabled();
  expect(within(row).getByRole("link", { name: /download/i })).toHaveAttribute("aria-disabled", "true");

  release(new Response(JSON.stringify({
    restored: true, backup_id: 1, filename: FILENAME, duration_ms: 1000,
    workers_quiesced: false, warning: "restart worker and beat",
  })));
  expect(await screen.findByText(/restored from/i)).toBeInTheDocument();
});

test.each([
  [403, "restore_disabled", "Restore from the UI is switched off", /turn on .allow restore from the ui./i],
  [409, "backup_in_progress", "A backup or restore is already running", /wait for it to finish/i],
  [409, "backup_not_restorable", "Backup status is 'failed'", /not in an .ok. state/i],
  [409, "backup_file_missing", "no such file", /gone from disk/i],
  [504, "restore_timeout", "pg_restore exceeded its 1800s limit", /past its 1800s limit/i],
])("a %i %s renders its own guidance", async (status, code, detail, guidance) => {
  restoreResponder = async () => errorResponse(status, { code, detail });
  const dialog = await openRestoreDialog();
  await userEvent.type(within(dialog).getByLabelText(/backup filename/i), FILENAME);
  await userEvent.click(restoreButton(dialog));

  const alert = await screen.findByRole("alert");
  expect(within(alert).getByText(guidance)).toBeInTheDocument();
  expect(within(alert).getByText(detail)).toBeInTheDocument();
  expect(within(alert).getByText(new RegExp(code))).toBeInTheDocument();
  // The dialog stays open so the user can correct and retry.
  expect(screen.getByRole("dialog", { name: /restore the database/i })).toBeInTheDocument();
});

test("a 403 points at the System settings switch", async () => {
  restoreResponder = async () =>
    errorResponse(403, { code: "restore_disabled", detail: "Restore from the UI is switched off." });
  const dialog = await openRestoreDialog();
  await userEvent.type(within(dialog).getByLabelText(/backup filename/i), FILENAME);
  await userEvent.click(restoreButton(dialog));

  const link = await screen.findByRole("link", { name: /system settings/i });
  expect(link).toHaveAttribute("href", "/settings/system");
});

test("a 400 confirmation mismatch shows the filename the server expected", async () => {
  restoreResponder = async () =>
    errorResponse(400, {
      code: "confirmation_mismatch",
      detail: "Type the backup filename exactly to confirm the restore.",
      expected: FILENAME,
    });
  const dialog = await openRestoreDialog();
  await userEvent.type(within(dialog).getByLabelText(/backup filename/i), FILENAME);
  await userEvent.click(restoreButton(dialog));

  const alert = await screen.findByRole("alert");
  expect(within(alert).getByText(/did not match the filename exactly/i)).toBeInTheDocument();
  expect(within(alert).getByText(/Expected:/)).toBeInTheDocument();
});

test("a 500 shows pg_restore's exit code and stderr", async () => {
  restoreResponder = async () =>
    errorResponse(500, {
      code: "restore_failed",
      detail: "pg_restore exited 1",
      exit_code: 1,
      stderr: "pg_restore: error: could not execute query",
    });
  const dialog = await openRestoreDialog();
  await userEvent.type(within(dialog).getByLabelText(/backup filename/i), FILENAME);
  await userEvent.click(restoreButton(dialog));

  const alert = await screen.findByRole("alert");
  expect(within(alert).getByText(/may be partially restored/i)).toBeInTheDocument();
  expect(within(alert).getByText(/exit code 1/i)).toBeInTheDocument();
  expect(within(alert).getByText(/could not execute query/)).toBeInTheDocument();
});

test("a request that never answers says the restore may still be running", async () => {
  restoreResponder = async () => { throw new TypeError("network error"); };
  const dialog = await openRestoreDialog();
  await userEvent.type(within(dialog).getByLabelText(/backup filename/i), FILENAME);
  await userEvent.click(restoreButton(dialog));

  const alert = await screen.findByRole("alert");
  expect(within(alert).getByText(/may still be running/i)).toBeInTheDocument();
  expect(within(alert).getByText(/HTTP —/)).toBeInTheDocument();
});

test("a 200 with an unreadable body is not reported as success", async () => {
  restoreResponder = async () => new Response(JSON.stringify({ ok: "sure" }));
  const dialog = await openRestoreDialog();
  await userEvent.type(within(dialog).getByLabelText(/backup filename/i), FILENAME);
  await userEvent.click(restoreButton(dialog));

  expect(await screen.findByRole("alert")).toHaveTextContent(/could not read/i);
  expect(screen.queryByText(/restored from/i)).not.toBeInTheDocument();
});

test("cancelling the restore dialog sends nothing", async () => {
  const dialog = await openRestoreDialog();
  // The shared spy accumulates calls across tests; only what happens next matters.
  const spy = vi.spyOn(globalThis, "fetch");
  spy.mockClear();
  await userEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
  expect(screen.queryByRole("dialog", { name: /restore the database/i })).not.toBeInTheDocument();
  expect(spy.mock.calls.some(([u]) => String(u).includes("/restore/"))).toBe(false);
});
