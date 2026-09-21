import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { CitationText } from "./CitationText";

const meta = {
  title: "Content/CitationText",
  component: CitationText,
  tags: ["ai-generated"],
  parameters: {
    docs: {
      description: {
        component:
          "The sources block under an assistant message. One numbered marker per " +
          "distinct citation, rendered straight from the `citation` frames the " +
          "thread channel delivered — nothing is looked up server-side. Renders " +
          "nothing at all when the message carried no citations.",
      },
    },
  },
} satisfies Meta<typeof CitationText>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The three shapes a citation arrives in: web url, unresolvable news id, document. */
export const MixedSources: Story = {
  args: {
    citations: [
      {
        location: "web_search_result_location",
        source: "https://example.com/markets/fed-minutes",
        title: "Fed minutes show a split committee",
        cited_text: "Several participants judged that further tightening may be warranted.",
      },
      {
        location: "search_result_location",
        source: "news://bzn-4821",
        title: "Chip names lead the tape higher",
        cited_text: "Semis outperformed the index by 140bp on the session.",
      },
      {
        location: "page_location",
        source: "",
        title: "AAPL 10-K FY2025.pdf",
        cited_text: "Services revenue grew 12% year over year.",
      },
    ],
  },
  play: async ({ canvas }) => {
    // Only the http(s) source is a link; the news id and the document are not.
    await expect(canvas.getAllByRole("link")).toHaveLength(1);
    await expect(canvas.getByTestId("citation-row-3")).toBeVisible();
  },
};

/** A long cited span is truncated so one citation can't push the message off-screen. */
export const LongCitedText: Story = {
  args: {
    citations: [
      {
        location: "search_result_location",
        source: "https://example.com/long",
        title: "A very thorough wire story",
        cited_text: "lorem ipsum dolor sit amet ".repeat(20),
      },
    ],
  },
};

/** No citations — the block renders nothing rather than an empty heading. */
export const NoCitations: Story = {
  args: { citations: [] },
  play: async ({ canvas }) => {
    await expect(canvas.queryByTestId("citations")).toBeNull();
  },
};
