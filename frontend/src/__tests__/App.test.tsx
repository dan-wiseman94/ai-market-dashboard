import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { queryClient } from "../hooks/queryClient";
import Dashboard from "../pages/Dashboard";
import Settings from "../pages/Settings";
import { renderWithProviders } from "./testUtils";

describe("pages", () => {
  it("renders Dashboard heading", () => {
    renderWithProviders(<Dashboard />, { client: queryClient });
    expect(screen.getByText(/Market context/i)).toBeInTheDocument();
  });

  it("renders Settings heading", () => {
    renderWithProviders(<Settings />, { client: queryClient });
    expect(screen.getByText(/Settings/i)).toBeInTheDocument();
  });
});
