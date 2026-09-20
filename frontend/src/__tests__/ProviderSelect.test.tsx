import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";

const mockUseProviderConfigs = vi.fn();
vi.mock("@/hooks/useProviderConfigs", () => ({ useProviderConfigs: () => mockUseProviderConfigs() }));

import ProviderSelect, { providerReadiness } from "@/components/ai/ProviderSelect";

const CFG = (o: object) => ({
  provider: "claude", base_url: "", default_model: "", enabled: true, supports_vision: true,
  daily_cost_cap_usd: "10", monthly_cost_cap_usd: null, api_key_present: false, ...o,
});

describe("ProviderSelect", () => {
  it("labels each provider with its readiness", async () => {
    mockUseProviderConfigs.mockReturnValue({ data: [
      CFG({ provider: "claude", api_key_present: true }),
      CFG({ provider: "openai", enabled: false, api_key_present: true }),
      CFG({ provider: "local", base_url: "" }),
    ] });
    const onChange = vi.fn();
    render(<ProviderSelect ariaLabel="Default provider" value="claude" onChange={onChange} emptyOption="Inherit" />);
    const sel = screen.getByLabelText("Default provider");
    const texts = Array.from(sel.querySelectorAll("option")).map((o) => o.textContent);
    expect(texts).toEqual(["Inherit", "Claude · ready", "OpenAI · disabled", "Local · no base URL"]);
    await userEvent.selectOptions(sel, "openai");
    expect(onChange).toHaveBeenCalledWith("openai");
    await userEvent.selectOptions(sel, "");
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("providerReadiness handles a missing config", () => {
    expect(providerReadiness(undefined, "openai")).toBe("no key");
    expect(providerReadiness(undefined, "local")).toBe("no base URL");
  });
});
