import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import FeatureGroup from "./FeatureGroup";
import type { FeatureItem } from "@/api/features";

const base = {
  group: "ai",
  order: 1,
  scope: "global",
  backing: "system_settings",
  value_type: "bool",
  editable: true,
  write_path: "/api/settings/",
  field: "demo",
  env_var: "DEMO",
  env_only_reason: "",
  costs_money: false,
  cost_note: "",
  retroactive: false,
  requires: [],
  requirement: null,
  provider_only: "",
  deep_link: "",
};

const toggle = (key: string, label: string, value: boolean, order: number): FeatureItem => ({
  kind: "toggle",
  ...base,
  key,
  label,
  summary: `What ${label.toLowerCase()} does, in one line.`,
  help: `Longer explanation of ${label.toLowerCase()}.`,
  order,
  value,
  default_value: true,
  shipped_default: true,
  override: value ? null : false,
  source: value ? "default" : "override",
});

const group = { key: "ai", label: "AI capabilities", blurb: "What the models may do.", order: 1 };

const meta = {
  title: "Settings/FeatureGroup",
  component: FeatureGroup,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "One section of Settings → Features. A `fieldset` with a `legend` rather than a heading plus a div: the legend is the accessible group name for every control inside it, which is what keeps ~90 switches from reading as one undifferentiated list. The legend is the only heading — a duplicate `h3` would announce the title twice.",
      },
    },
  },
  args: { onSave: () => {} },
} satisfies Meta<typeof FeatureGroup>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A populated group: legend, blurb, and one row per capability. */
export const Populated: Story = {
  args: {
    group,
    items: [
      toggle("a.failover", "Cross-provider failover", true, 1),
      toggle("a.routing", "Route by measured calibration", false, 2),
    ],
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("group", { name: "AI capabilities" })).toBeVisible();
    await expect(canvas.getAllByRole("switch")).toHaveLength(2);
  },
};

/** One row mid-save: only that row's control is disabled, the rest stay usable. */
export const OneRowSaving: Story = {
  args: {
    group,
    items: [
      toggle("a.failover", "Cross-provider failover", true, 1),
      toggle("a.routing", "Route by measured calibration", false, 2),
    ],
    pendingKey: "a.failover",
  },
  play: async ({ canvas }) => {
    const switches = canvas.getAllByRole("switch");
    await expect(switches[0]).toBeDisabled();
    await expect(switches[1]).toBeEnabled();
  },
};

/** Filtered down to nothing — the group says so instead of rendering an empty box. */
export const NothingMatches: Story = {
  args: { group, items: [] },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Nothing here matches.")).toBeVisible();
  },
};
