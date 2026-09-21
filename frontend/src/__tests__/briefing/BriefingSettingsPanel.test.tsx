import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { BriefingConfig } from "@/api/briefing";
import BriefingSettingsPanel from "@/components/briefing/BriefingSettingsPanel";
import { mockApi, renderWithProviders, type FetchMock } from "../testUtils";

const CONFIG: BriefingConfig = {
  enabled: true,
  synthesis_enabled: true,
  send_at_local: "08:30:00",
  profile: null,
  news_lookback_hours: 14,
  events_within_days: 7,
  updated_at: "2026-09-01T00:00:00Z",
};

let api: FetchMock;
afterEach(() => api?.restore());

function mount(overrides: Partial<BriefingConfig> = {}) {
  api = mockApi({
    "GET /api/briefings/config/": { ...CONFIG, ...overrides },
    "PATCH /api/briefings/config/": (body: unknown) => ({ ...CONFIG, ...(body as object) }),
    "GET /api/profiles/": [
      { id: 3, name: "Swing", style: "swing", default_includes: [], default_provider: "claude",
        default_model: "m", active: true },
    ],
  });
  renderWithProviders(<BriefingSettingsPanel />);
}

describe("BriefingSettingsPanel", () => {
  it("renders every config field from GET /api/briefings/config/", async () => {
    mount();
    expect(
      await screen.findByLabelText(/Run the morning briefing automatically/i),
    ).toBeChecked();
    expect(screen.getByLabelText(/Write an AI synthesis/i)).toBeChecked();
    expect(screen.getByLabelText(/Send at \(local\)/i)).toHaveValue("08:30");
    expect(screen.getByLabelText(/News lookback \(hours\)/i)).toHaveValue(14);
    expect(screen.getByLabelText(/Events within \(days\)/i)).toHaveValue(7);
    expect(screen.getByLabelText(/Trading profile/i)).toHaveValue("");
  });

  it("says plainly that the daily run calls the model", async () => {
    mount();
    const box = await screen.findByLabelText(/Run the morning briefing automatically/i);
    expect(box.getAttribute("aria-describedby")).toBeTruthy();
    expect(screen.getByText(/Once a day/i).textContent).toMatch(/calls a model/i);
    expect(screen.getByText(/one paid model call per briefing/i)).toBeInTheDocument();
  });

  it("PATCHes only the edited fields and then reports saved", async () => {
    mount();
    const save = await screen.findByRole("button", { name: /save settings/i });
    expect(save).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/Write an AI synthesis/i));
    fireEvent.change(screen.getByLabelText(/Events within \(days\)/i), { target: { value: "10" } });
    expect(screen.getByRole("status")).toHaveTextContent("Unsaved changes");

    fireEvent.click(save);
    await waitFor(() =>
      expect(api.calls.some((c) => c.method === "PATCH")).toBe(true),
    );
    const patch = api.calls.find((c) => c.method === "PATCH");
    expect(patch?.body).toEqual({ synthesis_enabled: false, events_within_days: 10 });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Saved"));
  });

  it("sends the chosen profile id, and null when cleared", async () => {
    mount({ profile: 3 });
    const select = await screen.findByLabelText(/Trading profile/i);
    await waitFor(() => expect(select).toHaveValue("3"));
    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: /save settings/i }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ profile: null }),
    );
  });
});
