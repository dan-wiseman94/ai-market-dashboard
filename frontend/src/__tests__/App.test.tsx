import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { queryClient } from "../hooks/queryClient";
import SettingsLayout from "../pages/settings/SettingsLayout";
import { renderWithProviders } from "./testUtils";

describe("pages", () => {

  it("renders Settings hub heading", () => {
    renderWithProviders(<SettingsLayout />, { client: queryClient });
    expect(screen.getByText(/Ledger · Settings/i)).toBeInTheDocument();
  });
});
