// frontend/src/__tests__/ProvidersSettings.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ProvidersSettings from "@/pages/settings/ProvidersSettings";

// ProviderCard is unit-tested separately; stub it to keep this test focused.
vi.mock("@/components/settings/ProviderCard", () => ({
  default: ({ provider }: { provider: string }) => <div data-testid={`pc-${provider}`} />,
}));

describe("ProvidersSettings", () => {
  it("renders a card for claude, openai and local under an AI Providers heading", () => {
    render(<ProvidersSettings />);
    expect(screen.getByRole("heading", { name: "AI Providers" })).toBeInTheDocument();
    expect(screen.getByTestId("pc-claude")).toBeInTheDocument();
    expect(screen.getByTestId("pc-openai")).toBeInTheDocument();
    expect(screen.getByTestId("pc-local")).toBeInTheDocument();
  });
});
