import { apiGet, apiPatch } from "./client";

export type SchwabStatus = {
  connected: boolean;
  expires_at: string | null;
  // Non-null when a stored credential exists but Schwab rejected it (401/403):
  // reads have silently fallen back to a free provider until the user reconnects.
  auth_error: string | null;
};
export const fetchSchwabStatus = () => apiGet<SchwabStatus>("/api/schwab/status/");
export const fetchSchwabAuthorizeUrl = () => apiGet<{ url: string }>("/api/schwab/authorize/");

export type SchwabAppConfig = {
  client_id: string;
  client_secret_present: boolean;
  configured: boolean;
};
export const fetchSchwabAppConfig = () => apiGet<SchwabAppConfig>("/api/schwab/app-config/");
export const updateSchwabAppConfig = (body: {
  client_id: string;
  client_secret_write?: string;
}) => apiPatch<SchwabAppConfig>("/api/schwab/app-config/", body);
