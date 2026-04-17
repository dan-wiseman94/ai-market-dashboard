const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = "error";
    let message = res.statusText;
    try {
      const body = await res.json();
      code = body.code ?? code;
      message = body.message ?? message;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return fetch(`${apiBase}${path}`, { credentials: "include" }).then(handle<T>);
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${apiBase}${path}`, {
    method: "POST",
    credentials: "include",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${apiBase}${path}`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function apiDelete(path: string): Promise<void> {
  return fetch(`${apiBase}${path}`, {
    method: "DELETE",
    credentials: "include",
  }).then(handle<void>);
}

export type HealthResponse = { status: "ok" };
export const fetchHealth = () => apiGet<HealthResponse>("/api/health/");
