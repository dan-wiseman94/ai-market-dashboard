import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";
import { Citation } from "./Citation";

const meta = {
  title: "Content/Citation",
  component: Citation,
  tags: ["ai-generated"],
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Inline citation marker, rendered from the `citation` frame on the thread " +
          "channel. The marker links out ONLY for an http(s) source. Everything else " +
          "— an unresolvable `news://<feed-id>` pseudo-URI, a document citation with " +
          "no source at all, or a lookalike scheme such as `httpevil://` — renders as " +
          "a bare marker whose title and cited text are its accessible label.",
      },
    },
  },
  argTypes: {
    index: { control: { type: "number", min: 1 }, description: "Citation number, shown as [n]." },
    source: {
      control: "text",
      description: "The citation's source: an http(s) url, `news://<feed-id>`, or \"\".",
    },
    title: { control: "text", description: "Citation title (part of the accessible label)." },
    snippet: { control: "text", description: "The cited text, appended to the label." },
  },
} satisfies Meta<typeof Citation>;

export default meta;
type Story = StoryObj<typeof meta>;

/** A web-search citation carries a real url, so the marker links out to it. */
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

/**
 * A news `search_result` citation for an item we had no article url for falls
 * back to `news://<feed-id>`. That id is the **external feed's** id, not a
 * `NewsItem` pk, and no endpoint resolves it — so there is nothing to link to
 * and the marker stays bare. The headline and cited text carry the meaning.
 */
export const UnresolvableNewsSource: Story = {
  args: {
    index: 2,
    source: "news://bzn-4821",
    title: "Fed minutes show a split committee",
    snippet: "Several participants judged that further tightening may be warranted",
  },
  play: async ({ canvas }) => {
    await expect(canvas.queryByRole("link")).toBeNull();
    await expect(canvas.getByTestId("citation-2")).toHaveAttribute(
      "aria-label",
      "Fed minutes show a split committee: Several participants judged that further tightening may be warranted",
    );
  },
};

/**
 * A document citation (a Files-API attachment) has no source at all — only the
 * document title — so the marker is bare and labelled by the title.
 */
export const DocumentSource: Story = {
  args: {
    index: 3,
    source: "",
    title: "AAPL 10-K FY2025.pdf",
    snippet: "Services revenue grew 12% year over year",
  },
  play: async ({ canvas }) => {
    await expect(canvas.queryByRole("link")).toBeNull();
  },
};

/**
 * Security: `source` is model-influenced text. A scheme that merely *starts
 * with* "http" is not a web link, so it must never become an href.
 */
export const LookalikeSchemeIsNotALink: Story = {
  args: {
    index: 4,
    source: "httpevil://example.com/pwn",
    title: "Suspicious source",
  },
  play: async ({ canvas }) => {
    await expect(canvas.queryByRole("link")).toBeNull();
  },
};
