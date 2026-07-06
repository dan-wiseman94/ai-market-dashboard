const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

// The backend speaks two error envelopes: the hand-rolled `{code, message}`
// shape (threads/thesis/portfolio/market `_error` helpers) and DRF-native
// errors — `{detail: "..."}` (exception handler / NotFound / PermissionDenied)
// or a field-keyed validation dict (`{rationale: ["This field is required."]}`,
// `{non_field_errors: [...]}`). Flatten the field dict into one readable line so
// server-side validation messages (e.g. the pre-trade-discipline errors) reach
// the toast instead of degrading to the bare status text ("Bad Request").
function flattenFieldErrors(body: Record<string, unknown>): string | null {
  const parts: string[] = [];
  for (const [key, val] of Object.entries(body)) {
    const msgs = Array.isArray(val) ? val : [val];
    for (const m of msgs) {
      if (typeof m === "string") {
        parts.push(key === "non_field_errors" ? m : `${key}: ${m}`);
      }
    }
  }
  return parts.length > 0 ? parts.join("; ") : null;
}

function parseErrorBody(body: unknown, fallback: string): { code: string; message: string } {
  let code = "error";
  let message = fallback;
  if (body && typeof body === "object") {
    const b = body as Record<string, unknown>;
    if (typeof b.code === "string") code = b.code;
    if (typeof b.message === "string") {
      message = b.message; // hand-rolled {code, message}
    } else if (typeof b.detail === "string") {
      message = b.detail; // DRF {detail: "..."}
    } else {
      const flat = flattenFieldErrors(b); // DRF field-keyed validation dict
      if (flat) message = flat;
    }
  }
  return { code, message };
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = "error";
    let message = res.statusText;
    try {
      const body = await res.json();
      ({ code, message } = parseErrorBody(body, res.statusText));
    } catch {
      // response body may be empty or non-JSON; fall back to status text
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const hasBody = body !== undefined;
  return fetch(`${apiBase}${path}`, {
    method,
    credentials: "include",
    headers: hasBody ? { "Content-Type": "application/json" } : undefined,
    body: hasBody ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function apiGet<T>(path: string): Promise<T> {
  // react-query rejects a query function that returns `undefined` ("Query data
  // cannot be undefined"). A "latest"-style GET that 204s on no-data (e.g.
  // /api/aieval/runs/latest/, /api/briefings/latest/) is handled as `undefined`
  // by request(); coalesce to `null` so "no content" reads as a real value.
  // apiDelete keeps its `void`/undefined contract — only GETs feed react-query.
  return request<T>("GET", path).then((v) => (v === undefined ? (null as T) : v));
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>("POST", path, body);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return request<T>("PATCH", path, body);
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>("PUT", path, body);
}

export function apiDelete(path: string): Promise<void> {
  return request<void>("DELETE", path);
}

export type HealthResponse = { status: "ok" };
export const fetchHealth = () => apiGet<HealthResponse>("/api/health/");
