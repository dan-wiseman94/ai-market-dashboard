import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import DataSourcesSettings from "@/pages/settings/DataSourcesSettings";
import { saveDataSourceKey, clearDataSourceKey } from "@/api/dataSources";
import { ToastProvider } from "@/hooks/useToast";
import { Toasts } from "@/components/Toasts";

const mockUseDataSources = vi.fn();
vi.mock("@/hooks/useDataSources", () => ({ useDataSources: () => mockUseDataSources() }));
vi.mock("@/api/dataSources", () => ({
  saveDataSourceKey: vi.fn(async () => ({ configured: true, fields_present: ["api_key"] })),
  clearDataSourceKey: vi.fn(async () => ({ configured: false, fields_present: [] })),
}));

const SOURCES = [
  {
    provider: "fred", label: "FRED", auth: "key", fields: ["api_key"],
    blurb: "Macro.", docs_url: "https://x", status: { configured: false, fields_present: [] },
  },
  {
    provider: "alpaca", label: "Alpaca", auth: "key_secret", fields: ["api_key", "api_secret"],
    blurb: "Quotes.", docs_url: "https://x",
    status: { configured: true, fields_present: ["api_key", "api_secret"] },
  },
  {
    provider: "edgar", label: "SEC EDGAR", auth: "none", fields: [],
    blurb: "Filings.", docs_url: "https://x", status: { configured: true, fields_present: [] },
  },
  {
    provider: "schwab", label: "Charles Schwab", auth: "oauth", fields: [],
    blurb: "Brokerage.", docs_url: "https://x", status: { configured: false, fields_present: [] },
  },
];

function renderWithProviders() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <DataSourcesSettings />
          <Toasts />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseDataSources.mockReturnValue({ data: { data_sources: SOURCES }, isLoading: false });
});

describe("DataSourcesSettings", () => {
  it("renders a card per data source", () => {
    renderWithProviders();
    expect(screen.getByText("FRED")).toBeInTheDocument();
    expect(screen.getByText("Alpaca")).toBeInTheDocument();
    expect(screen.getByText("SEC EDGAR")).toBeInTheDocument();
    expect(screen.getByText("Charles Schwab")).toBeInTheDocument();
  });

  it("keyless source shows no key input and a 'no key needed' pill", () => {
    renderWithProviders();
    expect(screen.getByText(/no key needed/i)).toBeInTheDocument();
    expect(screen.getByText(/ready to use — no key required/i)).toBeInTheDocument();
  });

  it("saves a key via the write-only API", async () => {
    renderWithProviders();
    await userEvent.type(screen.getByLabelText("FRED API key"), "abc123");
    const fred = screen.getByTestId("ds-card-fred");
    await userEvent.click(within(fred).getByRole("button", { name: /save/i }));
    expect(vi.mocked(saveDataSourceKey)).toHaveBeenCalledWith("fred", { api_key_write: "abc123" });
    expect(await screen.findByText(/fred saved/i)).toBeInTheDocument();
  });

  it("key+secret source shows two fields and a Clear button when configured", () => {
    renderWithProviders();
    expect(screen.getByLabelText("Alpaca API key")).toBeInTheDocument();
    expect(screen.getByLabelText("Alpaca API secret")).toBeInTheDocument();
    const alpaca = screen.getByTestId("ds-card-alpaca");
    expect(within(alpaca).getByRole("button", { name: /clear/i })).toBeInTheDocument();
  });

  it("clears a configured source", async () => {
    renderWithProviders();
    const alpaca = screen.getByTestId("ds-card-alpaca");
    await userEvent.click(within(alpaca).getByRole("button", { name: /clear/i }));
    expect(vi.mocked(clearDataSourceKey)).toHaveBeenCalledWith("alpaca");
  });
});
