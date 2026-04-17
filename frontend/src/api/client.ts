export type HealthResponse = { status: "ok" };

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${apiBase}/api/health/`, { credentials: "include" });
  if (!res.ok) throw new Error(`health ${res.status}`);
  return res.json() as Promise<HealthResponse>;
}
