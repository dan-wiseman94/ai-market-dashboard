import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import NewThesisPage from "@/pages/NewThesisPage";
import { mockApi, renderWithProviders } from "./testUtils";

describe("NewThesisPage", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("prefills ticker, direction and rationale from deep-link query params", async () => {
    const m = mockApi({ "GET /api/analytics/track-record": { available: false } });
    restore = m.restore;
    renderWithProviders(<NewThesisPage />, {
      initialEntries: [
        "/theses/new?ticker=nvda&direction=bullish&rationale=Gapped%20on%20capex",
      ],
      routePath: "/theses/new",
    });

    const ticker = (await screen.findByLabelText(/Ticker/i)) as HTMLInputElement;
    expect(ticker.value).toBe("NVDA");
    expect((screen.getByLabelText(/Direction/i) as HTMLSelectElement).value).toBe("bullish");
    expect((screen.getByLabelText(/Rationale/i) as HTMLTextAreaElement).value).toContain(
      "Gapped on capex",
    );
  });

  it("posts the prefilled + user-entered fields when submitted", async () => {
    const m = mockApi({
      "GET /api/analytics/track-record": { available: false },
      "POST /api/theses/": (body: unknown) => ({ id: 42, ...(body as object) }),
    });
    restore = m.restore;
    renderWithProviders(<NewThesisPage />, {
      initialEntries: ["/theses/new?ticker=NVDA&direction=bullish&rationale=x"],
      routePath: "/theses/new",
    });

    fireEvent.change(await screen.findByLabelText(/Title/i), {
      target: { value: "NVDA long" },
    });
    fireEvent.change(screen.getByLabelText(/What would invalidate/i), {
      target: { value: "close below 100" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create thesis/i }));

    await waitFor(() => {
      const post = m.calls.find((c) => c.method === "POST" && c.url.includes("/api/theses/"));
      expect(post).toBeTruthy();
      expect(post!.body).toMatchObject({
        ticker: "NVDA",
        direction: "bullish",
        rationale: "x",
        invalidation_note: "close below 100",
      });
    });
  });
});
