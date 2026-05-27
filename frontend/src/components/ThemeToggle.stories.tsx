import type { Meta, StoryObj } from "@storybook/react-vite";
import ThemeToggle from "./ThemeToggle";
import { ThemeProvider } from "@/hooks/useTheme";

const meta = {
  title: "Layout/ThemeToggle",
  component: ThemeToggle,
  parameters: { layout: "centered" },
  decorators: [(Story) => (<ThemeProvider><Story /></ThemeProvider>)],
} satisfies Meta<typeof ThemeToggle>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Cycles Light → Dark → System on click. */
export const Default: Story = {};
