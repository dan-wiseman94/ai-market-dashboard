import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import IntegrationsPanel from "@/components/settings/IntegrationsPanel";
import { mockApi, renderWithProviders, type FetchMock } from "./testUtils";

const TOOLS_OK = {
  jsonrpc: "2.0",
  id: 1,
  result: {
    tools: [
      { name: "house_view" },
      { name: "theses" },
      { name: "predictions" },
      { name: "recall_search" },
    ],
  },
};

let mock: FetchMock | undefined;
afterEach(() => {
  mock?.restore();
  vi.restoreAllMocks();
});

function render(handler: unknown) {
  mock = mockApi({ "POST /api/mcp/": handler });
  renderWithProviders(<IntegrationsPanel />);
}

describe("IntegrationsPanel — MCP server card", () => {
  it("lists the four read-only tools and the endpoint", async () => {
    render(TOOLS_OK);
    expect(await screen.findByText("house_view")).toBeInTheDocument();
    expect(screen.getByText("theses")).toBeInTheDocument();
    expect(screen.getByText("predictions")).toBeInTheDocument();
    expect(screen.getByText("recall_search")).toBeInTheDocument();
    expect(screen.getByTestId("mcp-endpoint").textContent).toMatch(/\/api\/mcp\/$/);
  });

  it("reports an unauthenticated server as having no token configured", async () => {
    render(TOOLS_OK);
    expect(await screen.findByText(/no token configured/i)).toBeInTheDocument();
    expect(screen.getByText(/before exposing the endpoint/i)).toBeInTheDocument();
  });

  it("reports a 401 probe as a configured token, and never renders a token value", async () => {
    render({ status: 401, code: "unauthorized", message: "Unauthorized" });
    expect(await screen.findByText(/^Token configured$/)).toBeInTheDocument();
    // Only the placeholder ever appears — the real value is never sent to the browser.
    expect(screen.getByText(/Bearer <your MCP_AUTH_TOKEN>/)).toBeInTheDocument();
  });

  it("says the token state is unknown when the endpoint cannot be reached", async () => {
    render({ status: 500, code: "error", message: "boom" });
    expect(await screen.findByRole("alert")).toHaveTextContent(/token state is unknown/i);
  });

  it("copies the client config to the clipboard", async () => {
    let copied = "";
    const writeText = vi.fn(async (text: string) => {
      copied = text;
    });
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(TOOLS_OK);
    await userEvent.click(await screen.findByRole("button", { name: /copy config/i }));
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(copied).toContain("ledger-second-brain");
    expect(await screen.findByRole("button", { name: /copied/i })).toBeInTheDocument();
  });
});
