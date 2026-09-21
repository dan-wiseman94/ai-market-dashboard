import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, afterEach } from "vitest";
import FeaturesSettings from "@/pages/settings/FeaturesSettings";
import type { FeatureRegistry } from "@/api/features";
import { mockApi, renderWithProviders, type FetchMock } from "./testUtils";

const base = {
  group: "ai",
  order: 1,
  scope: "global",
  backing: "system_settings",
  value_type: "bool",
  editable: true,
  write_path: "/api/settings/",
  field: "demo_field",
  env_var: "DEMO_FIELD",
  env_only_reason: "",
  costs_money: false,
  cost_note: "",
  retroactive: false,
  requires: [],
  requirement: null,
  provider_only: "",
  deep_link: "",
};

function registry(over: Partial<FeatureRegistry> = {}): FeatureRegistry {
  return {
    groups: [
      { key: "ai", label: "AI capabilities", blurb: "What models may do.", order: 1 },
      { key: "data", label: "Data & retention", blurb: "What is collected.", order: 2 },
    ],
    toggles: [
      {
        ...base,
        key: "ai.failover",
        label: "Cross-provider failover",
        summary: "Retry a failed run once on a secondary provider.",
        help: "Only before a token streams.",
        field: "ai_failover_enabled",
        value: true,
        default_value: true,
        shipped_default: true,
        override: null,
        source: "default",
      },
      {
        ...base,
        key: "strategy.anomaly_sweep",
        label: "Scheduled anomaly sweep",
        summary: "Scans watched tickers unasked.",
        help: "Autonomous.",
        order: 2,
        field: "anomaly_sweep_enabled",
        costs_money: true,
        cost_note: "Runs every 30 minutes on its own.",
        value: false,
        default_value: true,
        shipped_default: true,
        override: false,
        source: "override",
      },
    ],
    numbers: [
      {
        ...base,
        key: "ai.provider_timeout_seconds",
        label: "Provider request timeout",
        summary: "How long a provider call may hang.",
        help: "Async path.",
        group: "ai",
        order: 3,
        value_type: "float",
        backing: "env_only",
        editable: false,
        write_path: "",
        field: "",
        env_var: "AI_PROVIDER_TIMEOUT_SECONDS",
        env_only_reason: "Read at provider construction on the async streaming path.",
        value: 60,
        default_value: 60,
        shipped_default: 60,
        override: null,
        source: "default",
        min_value: null,
        max_value: null,
        unit: "seconds",
        is_float: true,
      },
      {
        ...base,
        key: "retention.ohlc",
        label: "OHLC bars",
        summary: "How long price bars are kept.",
        help: "Nightly purge.",
        group: "data",
        order: 1,
        value_type: "int",
        field: "retention_ohlc_days",
        value: 400,
        default_value: 400,
        shipped_default: 400,
        override: null,
        source: "default",
        min_value: 1,
        max_value: null,
        unit: "days",
        is_float: false,
      },
    ],
    texts: [],
    per_object: [
      {
        ...base,
        key: "profile.enable_tools",
        label: "AI tools (function calling)",
        summary: "Let this profile's runs call tools.",
        help: "Per profile.",
        order: 4,
        scope: "per_profile",
        backing: "model_field",
        editable: false,
        write_path: "",
        field: "enable_tools",
        env_var: "",
        deep_link: "/profiles",
        on: 4,
        total: 13,
        degraded: false,
        noun: "profiles",
      },
    ],
    ...over,
  };
}

let mock: FetchMock | undefined;

function renderPage(reg: FeatureRegistry = registry()) {
  mock = mockApi({
    "GET /api/features/": reg,
    "PATCH /api/settings/": {},
  });
  return renderWithProviders(<FeaturesSettings />);
}

afterEach(() => {
  mock?.restore();
  mock = undefined;
  vi.restoreAllMocks();
});

describe("FeaturesSettings", () => {
  it("renders one fieldset per group with the payload's copy", async () => {
    renderPage();
    const group = await screen.findByRole("group", { name: "AI capabilities" });
    expect(within(group).getByText("Cross-provider failover")).toBeInTheDocument();
    expect(
      within(group).getByText("Retry a failed run once on a secondary provider."),
    ).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Data & retention" })).toBeInTheDocument();
  });

  it("names every switch from its visible label", async () => {
    renderPage();
    expect(
      await screen.findByRole("switch", { name: "Cross-provider failover" }),
    ).toBeInTheDocument();
  });

  it("reports how many rows the filter is showing", async () => {
    renderPage();
    expect(await screen.findByText("5 of 5 shown")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search features"), "failover");
    await waitFor(() => expect(screen.getByText("1 of 5 shown")).toBeInTheDocument());
    expect(screen.queryByText("OHLC bars")).not.toBeInTheDocument();
  });

  it("filters to the rows that spend money", async () => {
    renderPage();
    await screen.findByText("Cross-provider failover");
    await userEvent.click(screen.getByRole("button", { name: "Spends money" }));
    await waitFor(() => expect(screen.getByText("1 of 5 shown")).toBeInTheDocument());
    expect(screen.getByText("Scheduled anomaly sweep")).toBeInTheDocument();
  });

  it("writes a toggle to the endpoint and field the payload names", async () => {
    renderPage();
    await userEvent.click(await screen.findByRole("switch", { name: "Cross-provider failover" }));
    await waitFor(() => {
      const patch = mock?.calls.find((c) => c.method === "PATCH");
      expect(patch?.url).toContain("/api/settings/");
      expect(patch?.body).toEqual({ ai_failover_enabled: false });
    });
  });

  it("resets an override by PATCHing null, labelled with the value it restores", async () => {
    renderPage();
    const reset = await screen.findByRole("button", { name: /reset to default \(on\)/i });
    await userEvent.click(reset);
    await waitFor(() => {
      const patch = mock?.calls.find((c) => c.method === "PATCH");
      expect(patch?.body).toEqual({ anomaly_sweep_enabled: null });
    });
  });

  it("confirms before arming something that spends money", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderPage();
    await userEvent.click(await screen.findByRole("switch", { name: "Scheduled anomaly sweep" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Runs every 30 minutes"));
    expect(mock?.calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("never confirms when turning something off", async () => {
    const confirm = vi.spyOn(window, "confirm");
    const reg = registry();
    reg.toggles[1].value = true;
    renderPage(reg);
    await userEvent.click(await screen.findByRole("switch", { name: "Scheduled anomaly sweep" }));
    expect(confirm).not.toHaveBeenCalled();
    await waitFor(() => expect(mock?.calls.some((c) => c.method === "PATCH")).toBe(true));
  });

  it("warns that the retroactive switch restates recorded history", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const reg = registry();
    reg.toggles[0] = { ...reg.toggles[0], value: false, retroactive: true };
    renderPage(reg);
    await userEvent.click(await screen.findByRole("switch", { name: "Cross-provider failover" }));
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("already computed under"));
  });

  it("shows an environment-only row read-only, with its reason visible", async () => {
    renderPage();
    expect(await screen.findByText("Environment only")).toBeInTheDocument();
    expect(
      screen.getByText("Read at provider construction on the async streaming path."),
    ).toBeInTheDocument();
    expect(screen.getByText("AI_PROVIDER_TIMEOUT_SECONDS")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton", { name: /provider request timeout/i })).toBeNull();
  });

  it("shows a per-object row as a rollup and a deep link, never a switch", async () => {
    renderPage();
    expect(await screen.findByText("On for 4 of 13 profiles")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Manage AI tools (function calling) in Profiles" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: /AI tools/ })).toBeNull();
  });

  it("says a degraded rollup is unavailable rather than claiming zero", async () => {
    const reg = registry();
    reg.per_object[0] = { ...reg.per_object[0], on: null, total: null, degraded: true };
    renderPage(reg);
    expect(await screen.findByText("Count unavailable")).toBeInTheDocument();
    expect(screen.queryByText(/0 of 0/)).not.toBeInTheDocument();
  });

  it("commits a number on blur, not on every keystroke", async () => {
    renderPage();
    const input = await screen.findByRole("spinbutton", { name: "OHLC bars" });
    await userEvent.clear(input);
    await userEvent.type(input, "120");
    expect(mock?.calls.some((c) => c.method === "PATCH")).toBe(false);
    await userEvent.tab();
    await waitFor(() => {
      const patch = mock?.calls.find((c) => c.method === "PATCH");
      expect(patch?.body).toEqual({ retention_ohlc_days: 120 });
    });
  });

  it("surfaces a rejected save instead of silently reverting", async () => {
    mock = mockApi({
      "GET /api/features/": registry(),
      "PATCH /api/settings/": { status: 400, message: "retention_ohlc_days must be >= 97" },
    });
    renderWithProviders(<FeaturesSettings />);
    await userEvent.click(await screen.findByRole("switch", { name: "Cross-provider failover" }));
    // The server's own message reaches both the toast and the live region: Toasts is a
    // role="region", not a live region, so a screen-reader user would otherwise miss it.
    expect(await screen.findByTestId("toast-error")).toHaveTextContent(/must be >= 97/);
    const announced = screen.getAllByRole("status").map((el) => el.textContent ?? "");
    expect(announced.join(" | ")).toMatch(/could not be saved\. retention_ohlc_days must be >= 97/);
  });

  it("explains itself when the registry cannot be loaded", async () => {
    mock = mockApi({ "GET /api/features/": { status: 500, message: "boom" } });
    renderWithProviders(<FeaturesSettings />);
    expect(await screen.findByText("Couldn't load the feature list")).toBeInTheDocument();
  });
});

describe("FeaturesSettings source", () => {
  // The page's whole point is that a capability added to the backend registry shows up
  // here with no frontend change. A hardcoded key is how that quietly stops being true.
  const FEATURE_KEY = new RegExp(
    '"(ai|observer|schedule|trigger|profile|provider|preset|section|retention|' +
      'briefing|thesis|lesson|spend|analytics|strategy|book|methodology|danger)\\.[a-z_]+"',
  );

  it.each([
    "../pages/settings/FeaturesSettings.tsx",
    "../components/settings/FeatureRow.tsx",
    "../components/settings/FeatureGroup.tsx",
    "../lib/featureGroups.ts",
  ])("%s hardcodes no feature key", (relative) => {
    const source = readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");
    expect(source).not.toMatch(FEATURE_KEY);
  });
});
