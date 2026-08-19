import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, userEvent } from "storybook/test";
import ThemeToggle from "./ThemeToggle";
import { ThemeProvider } from "@/hooks/useTheme";

const meta = {
  title: "Layout/ThemeToggle",
  component: ThemeToggle,
  tags: ["ai-generated"],
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Single-button theme switcher that cycles the app preference Light → Dark → System on click.",
      },
    },
  },
  decorators: [
    (Story) => (
      <ThemeProvider>
        <Story />
      </ThemeProvider>
    ),
  ],
} satisfies Meta<typeof ThemeToggle>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Cycles Light → Dark → System on click. The play normalizes to "light" first
 * (preference is provider state seeded from localStorage), then asserts the
 * aria-label + data-preference advance through each step.
 */
export const Default: Story = {
  args: {},
  play: async ({ canvas }) => {
    const btn = canvas.getByTestId("theme-toggle");

    // Normalize to a known base. Cycle order is light → dark → system → light,
    // so at most three clicks lands on "light" regardless of the seeded value.
    let guard = 0;
    while (btn.getAttribute("data-preference") !== "light" && guard < 4) {
      await userEvent.click(btn);
      guard += 1;
    }
    await expect(btn).toHaveAttribute("data-preference", "light");
    await expect(btn).toHaveAttribute("aria-label", "Theme: Light");

    await userEvent.click(btn);
    await expect(btn).toHaveAttribute("data-preference", "dark");
    await expect(btn).toHaveAttribute("aria-label", "Theme: Dark");

    // dark → system (resolved theme is appended in parens, e.g. "(dark)")
    await userEvent.click(btn);
    await expect(btn).toHaveAttribute("data-preference", "system");
    await expect(btn.getAttribute("aria-label")).toMatch(/^Theme: System \((light|dark)\)$/);
  },
};
