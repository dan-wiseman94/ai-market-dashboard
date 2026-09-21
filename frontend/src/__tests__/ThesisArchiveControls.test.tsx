import { describe, expect, it, vi, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ArchiveControls } from "@/pages/thesis-detail/ArchiveControls";
import { LocationProbe, mockApi, renderWithProviders } from "./testUtils";
import type { PostMortem, Thesis } from "@/api/thesis";

const THESIS: Thesis = {
  id: 1,
  title: "SPY hits 600",
  ticker: "SPY",
  direction: "bullish",
  rationale: "Strong momentum behind the index",
  conviction: 3,
  entry_price: "550.00",
  target_price: "600.00",
  invalidation_price: "520.00",
  horizon_days: 90,
  status: "open",
  profile_id: null,
  thread_id: 42,
  snapshot_id: null,
  review_thread_id: null,
  guard_enabled: false,
  guard_trigger_id: null,
  opened_at: "2026-05-01T00:00:00Z",
  closed_at: null,
  close_note: "",
  archived_at: null,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T00:00:00Z",
  postmortems: [] as PostMortem[],
};

const ARCHIVED: Thesis = { ...THESIS, archived_at: "2026-06-01T00:00:00Z" };

function renderControls(thesis: Thesis, nav?: { captured: string }) {
  return renderWithProviders(<ArchiveControls thesis={thesis} />, {
    initialEntries: ["/theses/1"],
    routes: nav
      ? [
          { path: "/theses/1", element: <ArchiveControls thesis={thesis} /> },
          {
            path: "*",
            element: (
              <LocationProbe
                onChange={(p) => {
                  nav.captured = p;
                }}
              />
            ),
          },
        ]
      : undefined,
    routePath: nav ? undefined : "/theses/1",
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ArchiveControls", () => {
  it("offers Archive for a live thesis and sends a plain DELETE", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({ "DELETE /api/theses/1/": undefined });
    renderControls(THESIS);

    await user.click(screen.getByRole("button", { name: /archive thesis/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].method).toBe("DELETE");
    expect(calls[0].url).not.toContain("purge");
  });

  it("says the thesis is archived and offers Restore instead", async () => {
    const user = userEvent.setup();
    const { calls } = mockApi({
      "POST /api/theses/1/restore/": { ...ARCHIVED, archived_at: null },
    });
    renderControls(ARCHIVED);

    expect(screen.getByRole("status")).toHaveTextContent(/archived/i);
    expect(screen.queryByRole("button", { name: /archive thesis/i })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /restore thesis/i }));
    await waitFor(() => expect(calls[0].url).toContain("/api/theses/1/restore/"));
  });

  it("keeps the permanent delete collapsed until it is opened", async () => {
    const user = userEvent.setup();
    mockApi({ "DELETE /api/theses/1/": undefined });
    renderControls(THESIS);

    const disclosure = screen.getByRole("button", { name: /delete permanently/i });
    expect(disclosure).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("purge-thesis-btn")).not.toBeVisible();

    await user.click(disclosure);
    expect(disclosure).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("purge-thesis-btn")).toBeVisible();
  });

  it("sends nothing when the confirm is declined", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const { calls } = mockApi({ "DELETE /api/theses/1/": undefined });
    renderControls(THESIS);

    await user.click(screen.getByRole("button", { name: /delete permanently/i }));
    await user.click(screen.getByTestId("purge-thesis-btn"));

    expect(calls).toHaveLength(0);
  });

  it("purges with ?purge=true and returns to the list", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { calls } = mockApi({ "DELETE /api/theses/1/": undefined });
    const nav = { captured: "" };
    renderControls(THESIS, nav);

    await user.click(screen.getByRole("button", { name: /delete permanently/i }));
    await user.click(screen.getByTestId("purge-thesis-btn"));

    await waitFor(() => expect(calls[0].url).toContain("purge=true"));
    await waitFor(() => expect(nav.captured).toBe("/theses"));
  });

  it("explains the 409 and stays on the page when post-mortems exist", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const message =
      "This thesis has 2 completed post-mortem(s) feeding your calibration. Archive it instead of deleting it.";
    mockApi({
      "DELETE /api/theses/1/": { status: 409, code: "postmortem_history", message },
    });
    const nav = { captured: "" };
    renderControls(THESIS, nav);

    await user.click(screen.getByRole("button", { name: /delete permanently/i }));
    await user.click(screen.getByTestId("purge-thesis-btn"));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    expect(nav.captured).toBe("");
  });
});
