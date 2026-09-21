import { ApiError, apiGet, apiPost, apiDelete } from "./client";
import type { Schemas } from "./generated";

export type Backup = {
  id: number; created_at: string; filename: string; size_bytes: number;
  sha256: string; kind: "scheduled" | "manual"; status: string; error: string;
};

export const fetchBackups = () =>
  apiGet<{ count: number; next: string | null; previous: string | null; results: Backup[] }>(
    "/api/backups/",
  );

export const runBackupNow = () => apiPost<{ queued: boolean }>("/api/backups/run/", {});

export const deleteBackup = (id: number) => apiDelete(`/api/backups/${id}/`);

/* ── Restore ──────────────────────────────────────────────────────────────────
 * `POST /api/backups/{id}/restore/` is the one destructive endpoint in the app:
 * pg_restore --clean drops and recreates every table. Its refusal envelope
 * (RestoreError) carries code-specific extras the shared client deliberately
 * discards — `expected` (the filename the user had to type), `exit_code` and
 * `stderr` (credential-scrubbed pg_restore output, the only diagnostic a failed
 * restore ever produces). Those are exactly what the operator needs, so this one
 * call reads the body itself instead of going through apiPost(), and raises an
 * ApiError subclass carrying the whole envelope.
 * ─────────────────────────────────────────────────────────────────────────── */

export type RestoreRequest = Schemas["RestoreRequest"];
export type RestoreResponse = Schemas["RestoreResponse"];
export type RestoreErrorBody = Schemas["RestoreError"];

/**
 * A refused or failed restore. `body.code` is the machine-readable reason —
 * every documented one is rendered distinctly by the Backups page.
 */
export class RestoreFailure extends ApiError {
  constructor(status: number, public readonly body: RestoreErrorBody) {
    super(status, body.code, body.detail);
    this.name = "RestoreFailure";
  }
}

// The server caps pg_restore at 1800s. A real restore is ~5s, so a request still
// open after ten minutes means the answer is never arriving cleanly — but the
// server may well still be restoring, which is what the UI has to say.
const RESTORE_CLIENT_TIMEOUT_MS = 600_000;

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function str(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function num(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

function toErrorBody(payload: unknown, status: number): RestoreErrorBody {
  const b = asRecord(payload);
  return {
    code: str(b.code) ?? "restore_error",
    detail: str(b.detail) ?? str(b.message) ?? `The server answered ${status}.`,
    expected: str(b.expected),
    exit_code: num(b.exit_code),
    stderr: str(b.stderr),
  };
}

function isRestoreResponse(payload: unknown): payload is RestoreResponse {
  const b = asRecord(payload);
  return (
    typeof b.restored === "boolean" &&
    typeof b.filename === "string" &&
    typeof b.duration_ms === "number" &&
    typeof b.workers_quiesced === "boolean" &&
    typeof b.warning === "string"
  );
}

/**
 * Restore the live database from a backup. `confirm` must equal the backup's own
 * filename byte for byte — anything else answers 400 and nothing is touched.
 * Throws {@link RestoreFailure} for every non-200 outcome, including the two
 * codes this client raises itself: `restore_no_response` and `restore_unreadable`.
 */
export async function restoreBackup(id: number, confirm: string): Promise<RestoreResponse> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), RESTORE_CLIENT_TIMEOUT_MS);
  const payload: RestoreRequest = { confirm };
  let res: Response;
  try {
    res = await fetch(`${apiBase}/api/backups/${id}/restore/`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
  } catch {
    // Aborted, dropped, or the server went away mid-restore. The restore itself
    // may have completed — the caller must not claim either way.
    throw new RestoreFailure(0, {
      code: "restore_no_response",
      detail: "The server never answered this request.",
    });
  } finally {
    clearTimeout(timer);
  }

  // A 500 from a proxy (or a connection cut mid-body) need not be JSON.
  const body: unknown = await res.json().catch(() => null);

  if (!res.ok) throw new RestoreFailure(res.status, toErrorBody(body, res.status));
  if (!isRestoreResponse(body)) {
    throw new RestoreFailure(res.status, {
      code: "restore_unreadable",
      detail: "The server answered 200 with a body this client could not read.",
    });
  }
  return body;
}
