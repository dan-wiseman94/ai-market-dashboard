import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, waitFor } from "storybook/test";
import { http, HttpResponse } from "msw";
import type { AiModel } from "@/api/ai";
import ModelCatalogPanel from "./ModelCatalogPanel";

// The panel reads GET /api/schwab/models/ through react-query, so MSW supplies a
// deterministic catalog (rows + the per-provider fallback map).
const models: AiModel[] = [
  {
    id: "claude-opus-5", name: "Claude Opus 5", provider: "claude",
    input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5,
    context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000,
  },
  {
    id: "claude-sonnet-5", name: "Claude Sonnet 5", provider: "claude",
    input_per_mtok: 2, output_per_mtok: 10, cached_per_mtok: 0.2,
    context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000,
  },
  {
    id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai",
    input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4,
    context_window: 1_050_000, supports_vision: true, max_payload_tokens: 300_000,
  },
];

const defaults = { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" };

const meta = {
  title: "Content/ModelCatalogPanel",
  component: ModelCatalogPanel,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    msw: {
      handlers: [
        http.get("/api/schwab/models/", () => HttpResponse.json({ models, defaults })),
      ],
    },
    docs: {
      description: {
        component:
          "Reference table of every model the backend catalog knows: per-MTok prices, context window, snapshot payload budget and vision support, grouped by provider with the fallback model marked. These numbers drive cost estimates, spend caps and payload pruning.",
      },
    },
  },
} satisfies Meta<typeof ModelCatalogPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The populated catalog: two Claude rows and one OpenAI row, defaults marked. */
export const Populated: Story = {
  play: async ({ canvas }) => {
    await waitFor(async () => {
      await expect(canvas.getByTestId("catalog-row-claude-opus-5")).toBeVisible();
    });
    await expect(canvas.getByText("GPT-5.6 Sol")).toBeVisible();
  },
};

/** Empty catalog — the explanatory footnote still stands on its own. */
export const Empty: Story = {
  parameters: {
    msw: {
      handlers: [
        http.get("/api/schwab/models/", () => HttpResponse.json({ models: [], defaults: {} })),
      ],
    },
  },
  play: async ({ canvas }) => {
    await waitFor(async () => {
      await expect(canvas.getByText(/billed at its provider's top rate/i)).toBeVisible();
    });
  },
};
