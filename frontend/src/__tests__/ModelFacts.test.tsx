import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));

import ModelFacts, { fmtTokens } from "@/components/ai/ModelFacts";

const DATA = { models: [
  { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude", input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000 },
], defaults: { claude: "claude-opus-5" } };

describe("ModelFacts", () => {
  it("formats token counts", () => {
    expect(fmtTokens(1_000_000)).toBe("1M");
    expect(fmtTokens(1_050_000)).toBe("1.05M");
    expect(fmtTokens(150_000)).toBe("150k");
    expect(fmtTokens(40_000)).toBe("40k");
  });

  it("shows prices, context, payload budget and the default pill", () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    render(<ModelFacts provider="claude" modelId="claude-opus-5" />);
    const line = screen.getByTestId("model-facts").textContent ?? "";
    expect(line).toContain("$5.00 in");
    expect(line).toContain("$0.50 cached");
    expect(line).toContain("$25.00 out");
    expect(line).toContain("1M ctx");
    expect(line).toContain("150k payload");
    expect(line).toContain("vision");
    expect(screen.getByText("default")).toBeInTheDocument();
  });

  it("explains unknown ids per provider", () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    render(<ModelFacts provider="openai" modelId="gpt-99" />);
    expect(screen.getByText(/not in catalog/i)).toBeInTheDocument();
  });

  it("describes local models as free", () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    render(<ModelFacts provider="local" modelId="llama3" />);
    expect(screen.getByText(/no API cost/i)).toBeInTheDocument();
  });
});
