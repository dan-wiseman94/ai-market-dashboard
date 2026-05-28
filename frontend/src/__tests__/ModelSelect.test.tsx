// frontend/src/__tests__/ModelSelect.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ModelSelect from "@/components/settings/ModelSelect";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));

const claudeModels = {
  models: [
    { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6", provider: "claude",
      input_per_mtok: 3, output_per_mtok: 15, cached_per_mtok: 0.3, context_window: 200000, supports_vision: true },
    { id: "claude-opus-4-8", name: "Claude Opus 4.8", provider: "claude",
      input_per_mtok: 15, output_per_mtok: 75, cached_per_mtok: 1.5, context_window: 200000, supports_vision: true },
  ],
};

beforeEach(() => mockUseAiModels.mockReturnValue({ data: claudeModels }));

describe("ModelSelect", () => {
  it("lists catalog models for the provider", () => {
    render(<ModelSelect provider="claude" value="claude-sonnet-4-6" onChange={() => {}} />);
    expect(screen.getByRole("option", { name: "Claude Sonnet 4.6" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Claude Opus 4.8" })).toBeInTheDocument();
  });

  it("selecting a catalog model emits its id", async () => {
    const onChange = vi.fn();
    render(<ModelSelect provider="claude" value="claude-sonnet-4-6" onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "claude-opus-4-8");
    expect(onChange).toHaveBeenCalledWith("claude-opus-4-8");
  });

  it("shows a custom text input when value is not in the catalog", () => {
    render(<ModelSelect provider="local" value="llama-3.1" onChange={() => {}} />);
    expect(screen.getByLabelText("Custom model id")).toHaveValue("llama-3.1");
  });
});

describe("ModelSelect — explicit models", () => {
  it("lists the explicit models prop instead of the catalog", () => {
    render(
      <ModelSelect provider="local" value="" models={["llama3", "mistral"]} onChange={() => {}} />,
    );
    expect(screen.getByRole("option", { name: "llama3" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "mistral" })).toBeInTheDocument();
    // catalog (claude) models are NOT shown
    expect(screen.queryByRole("option", { name: "Claude Sonnet 4.6" })).not.toBeInTheDocument();
  });

  it("falls back to the Custom input when the value isn't in the explicit list", () => {
    render(
      <ModelSelect provider="local" value="custom-x" models={["llama3"]} onChange={() => {}} />,
    );
    expect(screen.getByLabelText("Custom model id")).toHaveValue("custom-x");
  });
});
