import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));

import { pickModelFor, useCatalog } from "@/hooks/useCatalog";

const MODELS = [
  { id: "claude-opus-5", name: "Claude Opus 5", provider: "claude", input_per_mtok: 5, output_per_mtok: 25, cached_per_mtok: 0.5, context_window: 1_000_000, supports_vision: true, max_payload_tokens: 150_000 },
  { id: "claude-sonnet-5", name: "Claude Sonnet 5", provider: "claude", input_per_mtok: 2, output_per_mtok: 10, cached_per_mtok: 0.2, context_window: 1_000_000, supports_vision: true },
  { id: "gpt-5", name: "GPT-5", provider: "openai", input_per_mtok: 1.25, output_per_mtok: 10, cached_per_mtok: 0.125, context_window: 400_000, supports_vision: true },
];

describe("useCatalog", () => {
  it("prefers API defaults over the seed literals", () => {
    mockUseAiModels.mockReturnValue({ data: { models: MODELS, defaults: { claude: "claude-sonnet-5" } }, isLoading: false });
    const { result } = renderHook(() => useCatalog());
    expect(result.current.defaultFor("claude")).toBe("claude-sonnet-5");
    expect(result.current.defaultFor("openai")).toBe("gpt-5.6-sol"); // seed fallback
    expect(result.current.modelsFor("openai").map((m) => m.id)).toEqual(["gpt-5"]);
    expect(result.current.byId("claude-opus-5")?.max_payload_tokens).toBe(150_000);
  });

  it("pickModelFor uses the default when listed, else the first model, else blank", () => {
    mockUseAiModels.mockReturnValue({ data: { models: MODELS }, isLoading: false });
    const { result } = renderHook(() => useCatalog());
    expect(pickModelFor("claude", result.current)).toBe("claude-opus-5");
    expect(pickModelFor("openai", result.current)).toBe("gpt-5"); // gpt-5.6-sol not listed
    expect(pickModelFor("local", result.current)).toBe("");
  });
});
