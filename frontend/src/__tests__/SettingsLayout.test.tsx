import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect } from "vitest";
import SettingsLayout from "@/pages/settings/SettingsLayout";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<div>providers-outlet</div>} />
          <Route path="features" element={<div>features-outlet</div>} />
          <Route path="connections" element={<div>connections-outlet</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("SettingsLayout", () => {
  it("renders the rail links and the page title", () => {
    renderAt("/settings");
    const nav = screen.getByRole("navigation", { name: /settings sections/i });
    ["Features", "AI Providers", "Connections", "Backups", "Export"].forEach((label) => {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    });
    expect(screen.getByText(/Ledger · Settings/i)).toBeInTheDocument();
  });

  it("leads the rail with Features, the only route to the capability switches", () => {
    renderAt("/settings");
    const nav = screen.getByRole("navigation", { name: /settings sections/i });
    const links = within(nav).getAllByRole("link");
    expect(links[0]).toHaveAccessibleName("Features");
    expect(links[0]).toHaveAttribute("href", "/settings/features");
  });

  it("renders the features child route", () => {
    renderAt("/settings/features");
    expect(screen.getByText("features-outlet")).toBeInTheDocument();
  });

  it("renders the matched child route via Outlet", () => {
    renderAt("/settings");
    expect(screen.getByText("providers-outlet")).toBeInTheDocument();
    renderAt("/settings/connections");
    expect(screen.getByText("connections-outlet")).toBeInTheDocument();
  });
});
