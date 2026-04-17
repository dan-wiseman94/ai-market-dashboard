import { apiGet } from "./client";

export type SchwabStatus = { connected: boolean; expires_at: string | null };
export const fetchSchwabStatus = () => apiGet<SchwabStatus>("/api/schwab/status/");
export const fetchSchwabAuthorizeUrl = () => apiGet<{ url: string }>("/api/schwab/authorize/");
