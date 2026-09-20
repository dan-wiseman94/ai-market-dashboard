import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import AiAttribution from "@/components/ai/AiAttribution";

describe("AiAttribution", () => {
  it("renders provider name, model id, cost and qualifier", () => {
    render(<AiAttribution provider="openai" model="gpt-5.6-sol" cost="0.0123" qualifier="override" />);
    const pill = screen.getByTestId("ai-attribution");
    expect(pill.textContent).toBe("OpenAI · gpt-5.6-sol · $0.0123 (override)");
  });

  it("renders nothing without provider or model", () => {
    const { container } = render(<AiAttribution />);
    expect(container).toBeEmptyDOMElement();
  });
});
