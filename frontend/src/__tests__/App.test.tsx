import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { queryClient } from "../hooks/queryClient";
import Dashboard from "../pages/Dashboard";
import SettingsLayout from "../pages/settings/SettingsLayout";
import { renderWithProviders } from "./testUtils";

describe("pages", () => {
  it("renders Dashboard heading", () => {
    renderWithProviders(<Dashboard />, { client: queryClient });
    expect(screen.getByText(/Market context/i)).toBeInTheDocument();
  });

  it("renders Settings hub heading", () => {
    renderWithProviders(<SettingsLayout />, { client: queryClient });
    expect(screen.getByText(/Ledger · Settings/i)).toBeInTheDocument();
  });
});
