import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import FeatureRow from "./FeatureRow";
import type { FeatureItem } from "@/api/features";

const base = {
  key: "demo.row",
  label: "Demo capability",
  summary: "One line the user reads under the label.",
  help: "The expander body: what ON does, and what OFF costs you.",
  group: "ai",
  order: 1,
  scope: "global",
  backing: "system_settings",
  value_type: "bool",
  editable: true,
  write_path: "/api/settings/",
  field: "demo_row",
  env_var: "DEMO_ROW",
  env_only_reason: "",
  costs_money: false,
  cost_note: "",
  retroactive: false,
  requires: [],
  requirement: null,
  provider_only: "",
  deep_link: "",
};

const toggle = (over: Partial<Extract<FeatureItem, { kind: "toggle" }>> = {}): FeatureItem => ({
  kind: "toggle",
  ...base,
  value: true,
  default_value: true,
  shipped_default: true,
  override: null,
  source: "default",
  ...over,
});

const meta = {
  title: "Settings/FeatureRow",
  component: FeatureRow,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "One switchable capability on Settings → Features. Every word it renders comes from the `/api/features/` payload — the component hardcodes no feature name. Provenance is a badge plus a reset affordance rather than a third switch position, and a per-object setting shows a rollup and a deep link instead of a switch that would claim to be off.",
      },
    },
  },
  args: { onSave: () => {} },
} satisfies Meta<typeof FeatureRow>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Inheriting its default: a quiet `Default` pill, no reset offered. */
export const InheritingDefault: Story = {
  args: { item: toggle() },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("switch")).toBeChecked();
    await expect(canvas.getByText("Default")).toBeVisible();
    await expect(canvas.queryByRole("button", { name: /reset to default/i })).toBeNull();
  },
};

/** An explicit override: the badge flips and a reset naming the restored value appears. */
export const Overridden: Story = {
  args: { item: toggle({ value: false, override: false, source: "override" }) },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("switch")).not.toBeChecked();
    await expect(canvas.getByRole("button", { name: /reset to default \(on\)/i })).toBeVisible();
  },
};

/** Set in the environment — still switchable, but the page says where the value came from. */
export const FromEnvironment: Story = {
  args: { item: toggle({ source: "env" }) },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("From .env")).toBeVisible();
  },
};

/** Arming this bills a provider, so the row carries a badge and confirms on the way on. */
export const CostsMoney: Story = {
  args: {
    item: toggle({
      label: "Unattended sweep",
      value: false,
      costs_money: true,
      cost_note: "Runs every 30 minutes and can start investigations without you.",
    }),
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Spends AI $")).toBeVisible();
  },
};

/** Flipping it restates numbers already recorded — the strongest warning on the page. */
export const Retroactive: Story = {
  args: {
    item: toggle({
      label: "Dividend-adjusted math",
      value: false,
      default_value: false,
      shipped_default: false,
      retroactive: true,
      help: "Retroactive: it restates post-mortem, Scorecard and Mirror numbers already recorded.",
    }),
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Retroactive")).toBeVisible();
  },
};

/** Read-only because it is consumed on the async path: shown with its reason, not omitted. */
export const EnvironmentOnly: Story = {
  args: {
    item: {
      kind: "number",
      ...base,
      key: "demo.timeout",
      label: "Provider request timeout",
      value_type: "float",
      backing: "env_only",
      editable: false,
      write_path: "",
      env_var: "AI_PROVIDER_TIMEOUT_SECONDS",
      env_only_reason: "Read when the provider client is constructed, on the async path.",
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
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Environment only")).toBeVisible();
    await expect(canvas.getByText(/async path/)).toBeVisible();
    await expect(canvas.queryByRole("switch")).toBeNull();
  },
};

/** Gated on a connection: disabled, with a visible reason and a way to fix it. */
export const BlockedByConnection: Story = {
  args: {
    item: toggle({
      label: "TradingView tools",
      requirement: {
        id: "tradingview",
        label: "TradingView",
        satisfied: false,
        manage_path: "/settings/connections",
      },
    }),
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("switch")).toBeDisabled();
    await expect(canvas.getByRole("link", { name: /connect tradingview first/i })).toBeVisible();
  },
};

/** Lives on individual rows: a rollup and a link, never a switch that would lie. */
export const PerObjectRollup: Story = {
  args: {
    item: {
      kind: "per_object",
      ...base,
      key: "demo.per_profile",
      label: "AI tools",
      scope: "per_profile",
      backing: "model_field",
      editable: false,
      write_path: "",
      env_var: "",
      deep_link: "/profiles",
      on: 4,
      total: 13,
      degraded: false,
      noun: "profiles",
    },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("On for 4 of 13 profiles")).toBeVisible();
    await expect(canvas.queryByRole("switch")).toBeNull();
    await expect(canvas.getByRole("link", { name: /manage ai tools in profiles/i })).toBeVisible();
  },
};

/** The aggregate failed: "unavailable", never a confident `0 of 0`. */
export const PerObjectDegraded: Story = {
  args: {
    item: {
      kind: "per_object",
      ...base,
      key: "demo.per_profile_degraded",
      label: "AI tools",
      scope: "per_profile",
      backing: "model_field",
      editable: false,
      write_path: "",
      env_var: "",
      deep_link: "/profiles",
      on: null,
      total: null,
      degraded: true,
      noun: "profiles",
    },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Count unavailable")).toBeVisible();
    await expect(canvas.queryByText(/0 of 0/)).toBeNull();
  },
};

/** A bounded number: committed on blur or Enter, never per keystroke. */
export const NumberRow: Story = {
  args: {
    item: {
      kind: "number",
      ...base,
      key: "demo.cap",
      label: "Autonomous daily cap",
      value_type: "float",
      value: 5,
      default_value: 5,
      shipped_default: 5,
      override: null,
      source: "default",
      min_value: 0,
      max_value: null,
      unit: "USD",
      is_float: true,
    },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("spinbutton")).toHaveValue(5);
  },
};

/** A fixed set of options renders a select, so an invalid value is unreachable. */
export const ChoiceRow: Story = {
  args: {
    item: {
      kind: "text",
      ...base,
      key: "demo.provider",
      label: "Failover provider",
      value_type: "choice",
      value: "openai",
      default_value: "",
      shipped_default: "",
      override: "openai",
      source: "override",
      choices: [
        { value: "", label: "None" },
        { value: "claude", label: "Anthropic Claude" },
        { value: "openai", label: "OpenAI" },
      ],
      max_length: 32,
    },
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("combobox")).toHaveValue("openai");
    await expect(canvas.getByRole("button", { name: /reset to default \(none\)/i })).toBeVisible();
  },
};
