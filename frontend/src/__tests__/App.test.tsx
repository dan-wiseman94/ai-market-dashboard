import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { queryClient } from "../hooks/queryClient";
import Dashboard from "../pages/Dashboard";
import Settings from "../pages/Settings";

describe("pages", () => {
  it("renders Dashboard heading", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><Dashboard /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();
  });

  it("renders Settings heading", () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><Settings /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText(/Settings/i)).toBeInTheDocument();
  });
});
