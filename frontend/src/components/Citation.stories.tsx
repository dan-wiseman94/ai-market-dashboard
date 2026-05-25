import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { Citation } from "./Citation";

const meta = {
  component: Citation,
  tags: ["ai-generated"],
  parameters: { layout: "centered" },
} satisfies Meta<typeof Citation>;

export default meta;
type Story = StoryObj<typeof meta>;

/** An http source renders the marker as an external link to that URL. */
export const UrlSource: Story = {
  args: {
    index: 1,
    source: "https://example.com/markets/fed",
    title: "Fed holds rates steady",
  },
  play: async ({ canvas, args }) => {
    await expect(canvas.getByRole("link")).toHaveAttribute("href", args.source);
  },
};

/** A non-URL source (e.g. `news://`) renders a bare, link-less marker. */
export const NonUrlSource: Story = {
  args: {
    index: 2,
    source: "news://4821",
    title: "Internal headline",
  },
};

/** The snippet is folded into the marker's accessible label after the title. */
export const WithSnippet: Story = {
  args: {
    index: 2,
    source: "news://4821",
    title: "Fed minutes",
    snippet: "Rates held steady",
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByTestId("citation-2")).toHaveAttribute(
      "aria-label",
      "Fed minutes: Rates held steady",
    );
  },
};
