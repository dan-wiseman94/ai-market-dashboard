import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import ProviderModelPicker from "@/components/ProviderModelPicker";

vi.mock("@/hooks/useAiModels", () => ({
  useAiModels: () => ({
    data: {
      models: [
        { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6", provider: "claude", input_per_mtok: 3, output_per_mtok: 15, cached_per_mtok: 0.3, context_window: 200000, supports_vision: true },
        { id: "claude-opus-4-8", name: "Claude Opus 4.8", provider: "claude", input_per_mtok: 15, output_per_mtok: 75, cached_per_mtok: 1.5, context_window: 200000, supports_vision: true },
        { id: "gpt-5", name: "GPT-5", provider: "openai", input_per_mtok: 10, output_per_mtok: 40, cached_per_mtok: 1, context_window: 128000, supports_vision: true },
        { id: "gpt-5-mini", name: "GPT-5 mini", provider: "openai", input_per_mtok: 0.5, output_per_mtok: 2, cached_per_mtok: 0.05, context_window: 200000, supports_vision: true },
      ],
    },
  }),
}));

const baseValue = { provider: "claude", model: "claude-sonnet-4-6" };

describe("ProviderModelPicker", () => {
  it("renders provider options from data (unique providers)", () => {
    const onChange = vi.fn();
    render(<ProviderModelPicker value={baseValue} onChange={onChange} />);
    const providerSelect = screen.getAllByRole("combobox")[0];
    const options = Array.from(providerSelect.querySelectorAll("option")).map((o) => o.value);
    expect(options).toContain("claude");
    expect(options).toContain("openai");
    // no duplicates
    expect(new Set(options).size).toBe(options.length);
  });

  it("renders models for the current value.provider", () => {
    const onChange = vi.fn();
    render(<ProviderModelPicker value={baseValue} onChange={onChange} />);
    const modelSelect = screen.getAllByRole("combobox")[1];
    const options = Array.from(modelSelect.querySelectorAll("option")).map((o) => o.value);
    expect(options).toContain("claude-sonnet-4-6");
    expect(options).toContain("claude-opus-4-8");
    // openai models should not appear
    expect(options).not.toContain("gpt-5");
  });

  it("changing provider calls onChange with new provider and first model of that provider", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProviderModelPicker value={baseValue} onChange={onChange} />);
    const providerSelect = screen.getAllByRole("combobox")[0];
    await user.selectOptions(providerSelect, "openai");
    expect(onChange).toHaveBeenCalledTimes(1);
    const [newValue] = onChange.mock.calls[0];
    expect(newValue.provider).toBe("openai");
    // first model for openai in the mock data is gpt-5
    expect(newValue.model).toBe("gpt-5");
  });

  it("shows placeholder option when provider has no models in catalog", () => {
    const onChange = vi.fn();
    // Use a provider not in the mock data
    render(<ProviderModelPicker value={{ provider: "local", model: "" }} onChange={onChange} />);
    expect(screen.getByText("(no catalog models — type your own)")).toBeInTheDocument();
  });

  it("changing model calls onChange with updated model keeping same provider", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProviderModelPicker value={baseValue} onChange={onChange} />);
    const modelSelect = screen.getAllByRole("combobox")[1];
    await user.selectOptions(modelSelect, "claude-opus-4-8");
    expect(onChange).toHaveBeenCalledTimes(1);
    const [newValue] = onChange.mock.calls[0];
    expect(newValue.provider).toBe("claude");
    expect(newValue.model).toBe("claude-opus-4-8");
  });
});
