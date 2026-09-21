import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));
vi.mock("@/hooks/useProviderConfigs", () => ({ useProviderConfigs: () => ({ data: [] }) }));

import AiTargetPicker from "@/components/ai/AiTargetPicker";

const DATA = { models: [
  { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude", input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1_000_000, supports_vision: true },
  { id: "gpt-5.6-sol", name: "GPT-5.6 Sol", provider: "openai", input_per_mtok: 4, output_per_mtok: 20, cached_per_mtok: 0.4, context_window: 1_050_000, supports_vision: true },
  { id: "gpt-5-mini", name: "GPT-5 mini", provider: "openai", input_per_mtok: 0.25, output_per_mtok: 2, cached_per_mtok: 0.025, context_window: 400_000, supports_vision: true },
], defaults: { claude: "claude-opus-5", openai: "gpt-5.6-sol", local: "" } };

describe("AiTargetPicker", () => {
  it("switching provider lands on that provider's default model", async () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    const onChange = vi.fn();
    render(<AiTargetPicker value={{ provider: "claude", model: "claude-opus-5" }} onChange={onChange} />);
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "openai");
    expect(onChange).toHaveBeenCalledWith({ provider: "openai", model: "gpt-5.6-sol" });
  });

  it("inherit mode emits blanks and hides the model select", async () => {
    mockUseAiModels.mockReturnValue({ data: DATA });
    const onChange = vi.fn();
    const { rerender } = render(
      <AiTargetPicker value={{ provider: "claude", model: "claude-opus-5" }} onChange={onChange}
        inherit={{ label: "Inherit from profile — Claude · claude-opus-5" }} />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Provider"), "");
    expect(onChange).toHaveBeenCalledWith({ provider: "", model: "" });
    rerender(
      <AiTargetPicker value={{ provider: "", model: "" }} onChange={onChange}
        inherit={{ label: "Inherit from profile — Claude · claude-opus-5" }} />,
    );
    expect(screen.queryByLabelText("Model")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Provider")).toHaveValue("");
  });
});
