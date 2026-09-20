import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DataSourcesPanel from "@/components/settings/DataSourcesPanel";
import {
  saveDataSourceKey,
  clearDataSourceKey,
  testDataSourceKey,
  fetchDataSourceAuthorizeUrl,
  disconnectDataSource,
} from "@/api/dataSources";
import { updateSystemSettings } from "@/api/settings";
import { renderWithProviders } from "./testUtils";

const mockUseDataSources = vi.fn();
vi.mock("@/hooks/useDataSources", () => ({ useDataSources: () => mockUseDataSources() }));
vi.mock("@/api/dataSources", () => ({
  saveDataSourceKey: vi.fn(async () => ({ configured: true, fields_present: ["api_key"] })),
  clearDataSourceKey: vi.fn(async () => ({ configured: false, fields_present: [] })),
  testDataSourceKey: vi.fn(async () => ({ ok: true, message: "Key works." })),
  fetchDataSourceAuthorizeUrl: vi.fn(async () => ({ url: "https://tv/authorize?x=1" })),
  disconnectDataSource: vi.fn(async () => undefined),
}));
const mockUseSystemSettings = vi.fn();
vi.mock("@/hooks/useSystemSettings", () => ({ useSystemSettings: () => mockUseSystemSettings() }));
vi.mock("@/api/settings", () => ({ updateSystemSettings: vi.fn(async () => ({})) }));

const SOURCES = [
  {
    provider: "schwab", label: "Charles Schwab", auth: "oauth", fields: [],
    blurb: "B.", signup_url: "https://s", docs_url: "https://d",
    status: { configured: false, fields_present: [] },
  },
  {
    provider: "fred", label: "FRED", auth: "key", fields: ["api_key"],
    blurb: "Macro.", signup_url: "https://fred-key", docs_url: "https://d",
    status: { configured: false, fields_present: [] },
  },
  {
    provider: "alpaca", label: "Alpaca", auth: "key_secret", fields: ["api_key", "api_secret"],
    blurb: "Q.", signup_url: "https://alpaca-key", docs_url: "https://d",
    status: { configured: true, fields_present: ["api_key", "api_secret"] },
  },
  {
    provider: "edgar", label: "SEC EDGAR", auth: "none", fields: [],
    blurb: "F.", signup_url: "", docs_url: "https://d",
    status: { configured: true, fields_present: [] },
  },
  {
    provider: "tradingview", label: "TradingView", auth: "oauth", fields: [],
    blurb: "MCP.", signup_url: "https://tv-pricing", docs_url: "https://tv-docs",
    status: { configured: false, fields_present: [], auth_error: null },
  },
];

function renderPanel() {
  return renderWithProviders(<DataSourcesPanel />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseDataSources.mockReturnValue({ data: { data_sources: SOURCES }, isLoading: false });
  mockUseSystemSettings.mockReturnValue({ data: { tradingview_tools_enabled: false } });
});

describe("DataSourcesPanel", () => {
  it("renders the key/keyless sources but excludes Schwab (oauth)", () => {
    renderPanel();
    expect(screen.getByText("FRED")).toBeInTheDocument();
    expect(screen.getByText("Alpaca")).toBeInTheDocument();
    expect(screen.getByText("SEC EDGAR")).toBeInTheDocument();
    expect(screen.queryByText("Charles Schwab")).not.toBeInTheDocument();
  });

  it("links to getting a free key for key sources", () => {
    renderPanel();
    const fred = screen.getByTestId("ds-card-fred");
    expect(within(fred).getByRole("link", { name: /get a free key/i })).toHaveAttribute(
      "href",
      "https://fred-key",
    );
  });

  it("keyless source shows no key form and no 'get a key' link", () => {
    renderPanel();
    const edgar = screen.getByTestId("ds-card-edgar");
    expect(within(edgar).queryByRole("link", { name: /get a free key/i })).not.toBeInTheDocument();
    expect(within(edgar).getByText(/ready to use/i)).toBeInTheDocument();
  });

  it("saves a key (write-only)", async () => {
    renderPanel();
    await userEvent.type(screen.getByLabelText("FRED API key"), "abc123");
    const fred = screen.getByTestId("ds-card-fred");
    await userEvent.click(within(fred).getByRole("button", { name: /save/i }));
    expect(vi.mocked(saveDataSourceKey)).toHaveBeenCalledWith("fred", { api_key_write: "abc123" });
  });

  it("tests a configured key and shows the result", async () => {
    renderPanel();
    const alpaca = screen.getByTestId("ds-card-alpaca");
    await userEvent.click(within(alpaca).getByRole("button", { name: /test key/i }));
    expect(vi.mocked(testDataSourceKey)).toHaveBeenCalledWith("alpaca");
    expect(await screen.findByText("Key works.")).toBeInTheDocument();
  });

  it("clears a configured source", async () => {
    renderPanel();
    const alpaca = screen.getByTestId("ds-card-alpaca");
    await userEvent.click(within(alpaca).getByRole("button", { name: /clear/i }));
    expect(vi.mocked(clearDataSourceKey)).toHaveBeenCalledWith("alpaca");
  });

  it("marks env-backed fields and hides Clear when nothing is DB-saved", () => {
    mockUseDataSources.mockReturnValue({
      data: {
        data_sources: [
          {
            ...SOURCES[1], // fred
            status: { configured: true, fields_present: ["api_key"], env_fields: ["api_key"] },
          },
        ],
      },
      isLoading: false,
    });
    renderPanel();
    const fred = screen.getByTestId("ds-card-fred");
    expect(within(fred).getByLabelText("FRED API key")).toHaveAttribute(
      "placeholder",
      expect.stringMatching(/\.env/),
    );
    // Clear only deletes the DB row; with an env-only key it would be a no-op.
    expect(within(fred).queryByRole("button", { name: /clear/i })).not.toBeInTheDocument();
    expect(within(fred).getByRole("button", { name: /test key/i })).toBeInTheDocument();
  });

  it("renders the TradingView OAuth card with a Connect button and no key form", () => {
    renderPanel();
    const card = screen.getByTestId("ds-card-tradingview");
    expect(within(card).getByRole("button", { name: /connect tradingview/i })).toBeInTheDocument();
    expect(within(card).queryByLabelText(/api key/i)).not.toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: /disconnect/i })).not.toBeInTheDocument();
  });

  it("Connect fetches the authorize URL and opens it in a new tab", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderPanel();
    const card = screen.getByTestId("ds-card-tradingview");
    await userEvent.click(within(card).getByRole("button", { name: /connect tradingview/i }));
    expect(vi.mocked(fetchDataSourceAuthorizeUrl)).toHaveBeenCalledWith("tradingview");
    expect(open).toHaveBeenCalledWith("https://tv/authorize?x=1", "_blank", "noopener,noreferrer");
    open.mockRestore();
  });

  it("connected TradingView shows Test, Disconnect, the AI toggle, and an auth error", async () => {
    const connected = SOURCES.map((s) =>
      s.provider === "tradingview"
        ? { ...s, status: { configured: true, fields_present: [], auth_error: "TradingView rejected the stored token" } }
        : s,
    );
    mockUseDataSources.mockReturnValue({ data: { data_sources: connected }, isLoading: false });
    renderPanel();
    const card = screen.getByTestId("ds-card-tradingview");
    expect(within(card).getByRole("alert")).toHaveTextContent(/rejected the stored token/i);
    expect(within(card).getByRole("button", { name: /reconnect/i })).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: /test connection/i }));
    expect(vi.mocked(testDataSourceKey)).toHaveBeenCalledWith("tradingview");
    await userEvent.click(within(card).getByLabelText(/expose tradingview tools to the ai/i));
    expect(vi.mocked(updateSystemSettings)).toHaveBeenCalledWith({ tradingview_tools_enabled: true });
    await userEvent.click(within(card).getByRole("button", { name: /disconnect/i }));
    expect(vi.mocked(disconnectDataSource)).toHaveBeenCalledWith("tradingview");
  });
});
