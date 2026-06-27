import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn } from "storybook/test";
import Toggle from "./Toggle";

const meta = {
  title: "Primitives/Toggle",
  component: Toggle,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "An on/off switch button (role=\"switch\") that flips its boolean state and calls onChange with the next value.",
      },
    },
  },
  args: { label: "Enable tools", onChange: fn(), checked: false },
  argTypes: {
    checked: { control: "boolean", description: "Whether the switch is on." },
    label: { control: "text", description: "Accessible label (aria-label)." },
    disabled: { control: "boolean", description: "Disables interaction." },
    onChange: { description: "Fired with the next boolean state on click." },
  },
} satisfies Meta<typeof Toggle>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Off by default; clicking flips it on and reports `true`. */
export const Off: Story = {
  args: { checked: false },
  play: async ({ canvas, userEvent, args }) => {
    const sw = canvas.getByRole("switch", { name: "Enable tools" });
    await expect(sw).toHaveAttribute("aria-checked", "false");
    await userEvent.click(sw);
    await expect(args.onChange).toHaveBeenCalledWith(true);
  },
};

/** On state; clicking reports `false`. */
export const On: Story = {
  args: { checked: true },
  play: async ({ canvas, userEvent, args }) => {
    const sw = canvas.getByRole("switch", { name: "Enable tools" });
    await expect(sw).toHaveAttribute("aria-checked", "true");
    await userEvent.click(sw);
    await expect(args.onChange).toHaveBeenCalledWith(false);
  },
};

/** Disabled switches don't fire onChange. */
export const Disabled: Story = {
  args: { checked: false, disabled: true },
  play: async ({ canvas, userEvent, args }) => {
    const sw = canvas.getByRole("switch", { name: "Enable tools" });
    await expect(sw).toBeDisabled();
    await userEvent.click(sw);
    await expect(args.onChange).not.toHaveBeenCalled();
  },
};
