import { apiGet, apiPut, apiDelete } from "./client";

export type DataSourceAuth = "oauth" | "key" | "key_secret" | "none";

export interface DataSourceStatus {
  configured: boolean;
  fields_present: string[];
}

export interface DataSource {
  provider: string;
  label: string;
  auth: DataSourceAuth;
  fields: string[];
  blurb: string;
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
