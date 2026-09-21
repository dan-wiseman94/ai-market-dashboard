import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "@/api/client";
import DeskPage from "@/pages/DeskPage";
import { renderWithProviders } from "./testUtils";

const ENTRY = {
  id: 1,
  created_at: "2026-06-01T12:00:00Z",
  anomaly_type: "price_move",
  ticker: "NVDA",
  severity: 9,
  evidence: {},
  finding: "NVDA gapped on capex.",
  suggested_actions: [{ type: "convene_warroom", label: "Convene War Room on NVDA" }],
  status: "new",
  warroom_run_id: null,
  investigation_thread_id: null,
};

function describedText(el: HTMLElement): string {
  const id = String(el.getAttribute("aria-describedby") ?? "");
  return document.getElementById(id)?.textContent ?? "";
}

afterEach(() => vi.restoreAllMocks());

describe("DeskPage", () => {
  it("renders findings + suggested action", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([
      { id: 1, created_at: "2026-06-01T12:00:00Z", anomaly_type: "price_move", ticker: "NVDA", severity: 9, evidence: {}, finding: "NVDA gapped on capex.", suggested_actions: [{ type: "convene_warroom", label: "Convene War Room on NVDA" }], status: "new", warroom_run_id: null },
    ]);
    renderWithProviders(<DeskPage />);
    await waitFor(() => expect(screen.getByText(/NVDA gapped on capex/)).toBeInTheDocument());
    expect(screen.getByText(/Convene War Room on NVDA/)).toBeInTheDocument();
  });

  it("names the spend beside the sweep button before anything is clicked", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([]);
    renderWithProviders(<DeskPage />);
    const button = await screen.findByRole("button", { name: /run sweep/i });
    // The cost has to reach a screen reader too, so it is the button's description
    // rather than loose text that happens to sit nearby.
    expect(describedText(button)).toMatch(/billed model calls/i);
    expect(describedText(button)).toMatch(/AI_AUTONOMOUS_DAILY_CAP_USD/);
  });

  it("queues no sweep until the spend is confirmed", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([]);
    const post = vi.spyOn(client, "apiPost").mockResolvedValue({ created: 0 });
    renderWithProviders(<DeskPage />);

    await userEvent.click(await screen.findByRole("button", { name: /run sweep/i }));
    expect(screen.getByTestId("desk-sweep-confirm")).toHaveTextContent(/costs real money/i);
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(post).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: /run sweep/i }));
    await userEvent.click(screen.getByRole("button", { name: /yes, spend money/i }));
    await waitFor(() => expect(post).toHaveBeenCalledWith("/api/desk/sweep/"));
    // Fire-and-forget: the worker runs the sweep, so the banner never claims it is done.
    expect(await screen.findByTestId("desk-sweep-queued")).toHaveTextContent(/queued is not finished/i);
  });

  it("asks before convening a War Room and spends nothing when declined", async () => {
    vi.spyOn(client, "apiGet").mockResolvedValue([ENTRY]);
    const post = vi.spyOn(client, "apiPost").mockResolvedValue(ENTRY);
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    renderWithProviders(<DeskPage />);

    await userEvent.click(await screen.findByRole("button", { name: /Convene War Room on NVDA/ }));
    expect(String(confirmSpy.mock.calls[0]?.[0])).toMatch(/several billed model calls/i);
    expect(post).not.toHaveBeenCalled();
  });
});
