import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { mockApi, renderWithProviders, type FetchMock } from "./testUtils";
import TriggersListPage from "../pages/TriggersListPage";

const TRIGGERS = [
  {
    id: 1, name: "SPY>550", profile: 1,
    condition: { metric: "price", ticker: "SPY", op: ">", value: 550 },
    cooldown_seconds: 1800, enabled: true, last_fired_at: null, firings_count: 3,
    created_at: "2026-04-18T00:00:00Z", updated_at: "2026-04-18T00:00:00Z",
  },
];

let api: FetchMock;

beforeEach(() => {
  api = mockApi({
    "GET /api/triggers/": TRIGGERS,
    "PATCH /api/triggers/1/": { ...TRIGGERS[0], enabled: false },
    "DELETE /api/triggers/1/": undefined, // 204
    "POST /fire/": { task_id: "t" },
  });
});

describe("TriggersListPage", () => {
  it("renders the list with names and firings_count", async () => {
    renderWithProviders(<TriggersListPage />);
    await waitFor(() => expect(screen.getByText("SPY>550")).toBeInTheDocument());
    expect(screen.getByText(/3 firings/i)).toBeInTheDocument();
  });

  it("fires manual fire on button click (after confirm)", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    renderWithProviders(<TriggersListPage />);
    await waitFor(() => expect(screen.getByText("SPY>550")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /fire now/i }));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      expect(api.calls.some((c) => c.url.includes("/fire/"))).toBe(true);
    });
    confirmSpy.mockRestore();
  });

  it("shows empty state when no triggers", async () => {
    mockApi({ "GET /api/triggers/": [] });
    renderWithProviders(<TriggersListPage />);
    await waitFor(() => expect(screen.getByText(/no triggers yet/i)).toBeInTheDocument());
  });
});
