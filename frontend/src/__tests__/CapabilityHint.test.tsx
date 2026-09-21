import { describe, it, expect } from "vitest";
import { capabilityHint } from "@/components/ai/CapabilityHint";

describe("capabilityHint", () => {
  it("is silent on Claude", () => {
    expect(capabilityHint("thinking", "claude", true)).toBeNull();
    expect(capabilityHint("tools", "claude", false)).toBeNull();
  });
  it("flags Claude-only features on other providers", () => {
    expect(capabilityHint("thinking", "openai", true)).toBe("Claude only — ignored on OpenAI");
    expect(capabilityHint("memory", "local", true)).toBe("Claude only — ignored on Local");
  });
  it("flags tools only when the provider config has them off", () => {
    expect(capabilityHint("tools", "openai", true)).toBeNull();
    expect(capabilityHint("tools", "openai", false)).toBe("Tool use is off for OpenAI in Settings → AI Providers");
  });
});
