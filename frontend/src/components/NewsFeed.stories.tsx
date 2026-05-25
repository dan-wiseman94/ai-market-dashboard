import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import NewsFeed from "./NewsFeed";

const meta = {
  component: NewsFeed,
  tags: ["ai-generated"],
  parameters: { layout: "padded" },
} satisfies Meta<typeof NewsFeed>;

export default meta;
type Story = StoryObj<typeof meta>;

const DAY = 86_400;
const BASE = 1_700_000_000;

/** Headlines render newest-first regardless of input order. */
export const Populated: Story = {
  args: {
    items: [
      { id: 1, headline: "Jobs report beats estimates", source: "WSJ", url: "https://example.com/jobs", datetime: BASE - DAY },
      { id: 2, headline: "Fed holds rates steady", source: "Reuters", url: "https://example.com/fed", datetime: BASE },
      { id: 3, headline: "Oil slips on demand worries", source: "Bloomberg", url: "https://example.com/oil", datetime: BASE - 2 * DAY },
    ],
  },
  play: async ({ canvas }) => {
    // The component sorts by datetime desc — the newest item leads the list.
    const links = canvas.getAllByRole("link");
    await expect(links[0]).toHaveTextContent("Fed holds rates steady");
  },
};

/** No items — the quiet empty state. */
export const Empty: Story = {
  args: { items: [] },
};
