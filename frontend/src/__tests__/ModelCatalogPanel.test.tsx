import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));

import ModelCatalogPanel from "@/components/settings/ModelCatalogPanel";

const DATA = {
  models: [
    {
      id: "claude-opus-5", name: "Claude Opus 5", provider: "claude",
      input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5,
      context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000,
    },
    {
      id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai",
      input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4,
      context_window: 1_050_000, supports_vision: true, max_payload_tokens: 300_000,
    },
  ],
  defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" },
};

beforeEach(() => vi.clearAllMocks());

describe("ModelCatalogPanel", () => {
  it("lists every catalog model with prices, budgets and the default marker", () => {
    mockUseAiModels.mockReturnValue({ data: DATA, isLoading: false });
    render(<ModelCatalogPanel />);

    expect(screen.getByRole("heading", { name: /model catalog/i })).toBeInTheDocument();
    const opus = screen.getByTestId("catalog-row-claude-opus-5");
    expect(opus.textContent).toContain("$5.00");
    expect(opus.textContent).toContain("$0.50");
    expect(opus.textContent).toContain("$25.00");
    expect(opus.textContent).toContain("1M");
    expect(opus.textContent).toContain("150k");
    expect(opus.textContent).toContain("default");
    expect(screen.getByTestId("catalog-row-gpt-5.6-sol").textContent).toContain("1.05M");
    expect(screen.getByText(/billed at its provider's top rate/i)).toBeInTheDocument();
  });

  it("falls back to the 40k budget for a row the API sent without one", () => {
    mockUseAiModels.mockReturnValue({
      data: { models: [{ ...DATA.models[0], max_payload_tokens: undefined }], defaults: {} },
      isLoading: false,
    });
    render(<ModelCatalogPanel />);
    expect(screen.getByTestId("catalog-row-claude-opus-5").textContent).toContain("40k");
  });

  it("renders skeleton rows while the catalog loads", () => {
    mockUseAiModels.mockReturnValue({ data: undefined, isLoading: true });
    render(<ModelCatalogPanel />);
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
  });
});
