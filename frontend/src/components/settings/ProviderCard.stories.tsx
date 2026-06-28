import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, waitFor } from "storybook/test";
import { http, HttpResponse } from "msw";
import type { AiModel, ProviderConfig } from "@/api/ai";
import type { CapRow } from "@/api/costs";
import { ToastProvider } from "@/hooks/useToast";
import ProviderCard from "./ProviderCard";

// ProviderCard self-fetches its stored config (GET /api/schwab/providers/),
// today's spend (GET /api/schwab/usage/) and the cap meters (GET /api/costs/caps),
// then renders an editable form. These stories mock those endpoints with MSW so
// the Claude / OpenAI / Local variants render deterministically.
const configs: ProviderConfig[] = [
  {
    provider: "claude",
    base_url: "",
    default_model: "claude-sonnet-4-6",
    enabled: true,
    supports_vision: true,
    daily_cost_cap_usd: "10.00",
    monthly_cost_cap_usd: "100.00",
    api_key_present: true,
    discovered_models: [],
  },
  {
    provider: "openai",
    base_url: "",
    default_model: "gpt-5",
    enabled: true,
    supports_vision: true,
    daily_cost_cap_usd: "8.00",
    monthly_cost_cap_usd: null,
    api_key_present: false,
    discovered_models: [],
  },
  {
    provider: "local",
    base_url: "http://host.docker.internal:11434/v1",
    default_model: "llama-3.1-70b",
    enabled: true,
    supports_vision: false,
    daily_cost_cap_usd: "0.00",
    monthly_cost_cap_usd: null,
    api_key_present: false,
    discovered_models: ["llama-3.1-70b", "qwen2.5-7b"],
  },
];

const caps: CapRow[] = [
  {
    provider: "claude",
    daily: { cap: "10.00", spent: "1.23", pct: 0.123 },
    monthly: { cap: "100.00", spent: "12.34", pct: 0.1234 },
  },
  {
    provider: "openai",
    daily: { cap: "8.00", spent: "0.42", pct: 0.0525 },
    monthly: null,
  },
];

const mtok = { input_per_mtok: 3, output_per_mtok: 15, cached_per_mtok: 0.3, context_window: 200_000, supports_vision: true };
const models: AiModel[] = [
  { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6", provider: "claude", ...mtok },
  { id: "gpt-5", name: "GPT-5", provider: "openai", ...mtok },
];

const baseHandlers = [
  http.get("/api/schwab/providers/", () => HttpResponse.json(configs)),
  http.get("/api/schwab/usage/", () => HttpResponse.json({ today: { claude: "1.23", openai: "0.42", local: "0" } })),
  http.get("/api/costs/caps", () => HttpResponse.json(caps)),
  http.get("/api/schwab/models/", () => HttpResponse.json({ models })),
  http.post("/api/schwab/providers/local/probe/", () =>
    HttpResponse.json({ ok: true, models: ["llama-3.1-70b", "qwen2.5-7b"] }),
  ),
];

const meta = {
  title: "Content/ProviderCard",
  component: ProviderCard,
  tags: ["ai-generated"],
  parameters: {
    layout: "padded",
    msw: { handlers: baseHandlers },
    docs: {
      description: {
        component:
          "A per-provider AI config card/form. Fetches the stored ProviderConfig, today's spend and cap meters via react-query (mocked here with MSW), then renders an editable API-key / model / cost-cap form. The Local variant swaps caps for a base-URL field with a connection probe.",
      },
    },
  },
  argTypes: {
    provider: {
      control: "select",
      options: ["claude", "openai", "local"],
      description: "Which provider this card configures.",
    },
  },
  // The Save / toggle handlers call useToast().push, which throws without a
  // ToastProvider (the global preview supplies only QueryClient + router).
  decorators: [
    (Story) => (
      <ToastProvider defaultDurationMs={1_000_000}>
        <Story />
      </ToastProvider>
    ),
  ],
} satisfies Meta<typeof ProviderCard>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Claude with a stored key: the "key set" pill, cost-cap fields, and cap meters. */
export const Claude: Story = {
  args: { provider: "claude" },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("key set ••••")).toBeVisible();
    await expect(canvas.getByRole("heading", { name: "Claude" })).toBeVisible();
    await expect(canvas.getByText("Daily cap (USD)")).toBeVisible();
    await expect(canvas.getByRole("button", { name: "Save" })).toBeVisible();
  },
};

/** OpenAI with no key stored yet — the "no key" pill and a blank monthly cap. */
export const OpenAI: Story = {
  args: { provider: "openai" },
  play: async ({ canvas }) => {
    await expect(await canvas.findByText("no key")).toBeVisible();
    await expect(canvas.getByRole("heading", { name: "OpenAI" })).toBeVisible();
  },
};

/**
 * Local: a base-URL field (no cost caps) with a "Test connection" probe. Clicking
 * it POSTs to the probe endpoint and surfaces the discovered-model count.
 */
export const Local: Story = {
  args: { provider: "local" },
  play: async ({ canvas, userEvent }) => {
    await expect(await canvas.findByText(/runs on your machine/i)).toBeVisible();
    await expect(canvas.getByText("Base URL")).toBeVisible();
    const probe = await canvas.findByRole("button", { name: /test connection/i });
    await waitFor(() => expect(probe).toBeEnabled());
    await userEvent.click(probe);
    await expect(await canvas.findByText(/2 models found/i)).toBeVisible();
  },
};
