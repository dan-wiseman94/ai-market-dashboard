import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ProvidersSettings from "@/pages/settings/ProvidersSettings";

// ProviderCard and ModelCatalogPanel are unit-tested separately; stub both to keep
// this test on the page's own composition (and off their react-query fetches).
vi.mock("@/components/settings/ProviderCard", () => ({
  default: ({ provider }: { provider: string }) => <div data-testid={`pc-${provider}`} />,
}));
vi.mock("@/components/settings/ModelCatalogPanel", () => ({
  default: () => <div data-testid="catalog-panel" />,
}));

describe("ProvidersSettings", () => {
  it("renders a card for claude, openai and local under an AI Providers heading", () => {
    render(<ProvidersSettings />);
    expect(screen.getByRole("heading", { name: "AI Providers" })).toBeInTheDocument();
    expect(screen.getByTestId("pc-claude")).toBeInTheDocument();
    expect(screen.getByTestId("pc-openai")).toBeInTheDocument();
    expect(screen.getByTestId("pc-local")).toBeInTheDocument();
    expect(screen.getByTestId("catalog-panel")).toBeInTheDocument();
  });
});
