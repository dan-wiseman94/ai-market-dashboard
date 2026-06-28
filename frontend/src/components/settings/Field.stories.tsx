import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import Field from "./Field";

/** A sample control wired through the render-prop `{ id, describedBy }`. */
const renderInput = ({ id, describedBy }: { id: string; describedBy?: string }) => (
  <input
    id={id}
    aria-describedby={describedBy}
    defaultValue="200"
    inputMode="decimal"
    className="w-44 rounded border border-ink-700 bg-ink-900 px-2 py-1 text-sm text-ink-100"
  />
);

const meta = {
  title: "Primitives/Field",
  component: Field,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Labeled form-field wrapper: renders a mono uppercase label, hands its render-prop children a generated `id` (wired to the label via `htmlFor`) plus a `describedBy` token, and shows an optional hint or a mutually-exclusive error message beneath the control.",
      },
    },
  },
  args: { label: "Monthly cap (USD)", children: renderInput },
  argTypes: {
    label: { control: "text", description: "Field label, rendered uppercase in mono." },
    hint: {
      control: "text",
      description: "Helper text shown below the control when there is no error.",
    },
    error: {
      control: "text",
      description: "Error text; replaces the hint and is referenced via aria-describedby.",
    },
    children: {
      control: false,
      description: "Render-prop receiving { id, describedBy } for the control.",
    },
  },
} satisfies Meta<typeof Field>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Bare label + control; the generated id associates the label with the input. */
export const Default: Story = {
  play: async ({ canvas }) => {
    const control = canvas.getByLabelText("Monthly cap (USD)");
    await expect(control).toBeInTheDocument();
  },
};

/** Helper text appears below the control. */
export const WithHint: Story = {
  args: { hint: "Leave blank for no cap." },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Leave blank for no cap.")).toBeInTheDocument();
  },
};

/** An error replaces the hint (they are mutually exclusive). */
export const WithError: Story = {
  args: {
    hint: "Leave blank for no cap.",
    error: "Must be a positive number.",
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByText("Must be a positive number.")).toBeInTheDocument();
    await expect(canvas.queryByText("Leave blank for no cap.")).toBeNull();
  },
};
