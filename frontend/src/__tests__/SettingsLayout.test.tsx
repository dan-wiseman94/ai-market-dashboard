// frontend/src/__tests__/SettingsLayout.test.tsx
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
    ["AI Providers", "Connections", "Backups", "Export"].forEach((label) => {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    });
    expect(screen.getByText(/Ledger · Settings/i)).toBeInTheDocument();
  });

  it("renders the matched child route via Outlet", () => {
    renderAt("/settings");
    expect(screen.getByText("providers-outlet")).toBeInTheDocument();
    renderAt("/settings/connections");
    expect(screen.getByText("connections-outlet")).toBeInTheDocument();
  });
});
