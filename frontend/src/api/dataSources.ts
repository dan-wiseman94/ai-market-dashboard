import { apiGet, apiPost, apiPut, apiDelete } from "./client";

export type DataSourceAuth = "oauth" | "key" | "key_secret" | "none";

export interface DataSourceStatus {
  configured: boolean;
  fields_present: string[];
  /** Subset of fields_present currently supplied by a host .env var rather than a saved key. */
  env_fields?: string[];
  /** OAuth sources only: the provider rejected the stored token; reconnect to clear. */
  auth_error?: string | null;
}

export interface DataSource {
  provider: string;
  label: string;
  auth: DataSourceAuth;
  fields: string[];
  blurb: string;
  signup_url: string;
  docs_url: string;
  status: DataSourceStatus;
}

export const fetchDataSources = () =>
  apiGet<{ data_sources: DataSource[] }>("/api/schwab/data-sources/");

/** Save API key(s) for a key-based source. Body keys are `<field>_write` (write-only). */
export const saveDataSourceKey = (provider: string, body: Record<string, string>) =>
  apiPut<DataSourceStatus>(`/api/schwab/data-sources/${provider}/`, body);

export const clearDataSourceKey = (provider: string) =>
  apiDelete(`/api/schwab/data-sources/${provider}/`);

export interface TestResult {
  ok: boolean;
  message: string;
}

/** Probe the saved credential to check whether the key actually works. */
export const testDataSourceKey = (provider: string) =>
  apiPost<TestResult>(`/api/schwab/data-sources/${provider}/test/`, {});

/** OAuth sources (TradingView): the consent URL to open in a new tab. */
export const fetchDataSourceAuthorizeUrl = (provider: string) =>
  apiGet<{ url: string }>(`/api/schwab/data-sources/${provider}/authorize/`);

/** OAuth sources: revoke upstream (best-effort) and forget the token. */
export const disconnectDataSource = (provider: string) =>
  apiDelete(`/api/schwab/data-sources/${provider}/`);
