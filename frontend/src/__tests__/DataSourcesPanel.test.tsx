import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DataSourcesPanel from "@/components/settings/DataSourcesPanel";
import { saveDataSourceKey, clearDataSourceKey, testDataSourceKey } from "@/api/dataSources";
import { renderWithProviders } from "./testUtils";

const mockUseDataSources = vi.fn();
vi.mock("@/hooks/useDataSources", () => ({ useDataSources: () => mockUseDataSources() }));
vi.mock("@/api/dataSources", () => ({
  saveDataSourceKey: vi.fn(async () => ({ configured: true, fields_present: ["api_key"] })),
  clearDataSourceKey: vi.fn(async () => ({ configured: false, fields_present: [] })),
  testDataSourceKey: vi.fn(async () => ({ ok: true, message: "Key works." })),
}));

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
];

function renderPanel() {
  return renderWithProviders(<DataSourcesPanel />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseDataSources.mockReturnValue({ data: { data_sources: SOURCES }, isLoading: false });
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
});
