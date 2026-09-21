import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import LessonsPage from "@/pages/LessonsPage";
import { mockApi, renderWithProviders, type FetchMock } from "./testUtils";

const SUPPORTED = {
  id: 1,
  text: "I add to losers into the close.",
  tags: { directions: ["bullish"], sectors: [] },
  support_n: 4,
  muted: false,
  pinned: false,
  visible_to_coach: true,
  last_seen: "2026-06-01T00:00:00Z",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

const THIN = {
  id: 2,
  text: "I trust the first 5-minute candle too much.",
  tags: { directions: [], sectors: ["Energy"] },
  support_n: 1,
  muted: false,
  pinned: false,
  visible_to_coach: false,
  last_seen: null,
  created_at: "2026-05-02T00:00:00Z",
  updated_at: "2026-05-02T00:00:00Z",
};

let api: FetchMock;

afterEach(() => {
  api?.restore();
  vi.restoreAllMocks();
});

describe("LessonsPage", () => {
  it("separates the lessons reaching the Coach from the ones filtered out", async () => {
    api = mockApi({ "GET /api/lessons/": [SUPPORTED, THIN] });
    renderWithProviders(<LessonsPage />);

    await waitFor(() =>
      expect(screen.getByText(/I add to losers into the close/)).toBeInTheDocument(),
    );
    expect(screen.getByText("Reaching the Coach")).toBeInTheDocument();
    expect(screen.getByText("Not reaching the Coach")).toBeInTheDocument();
    // The threshold is spelled out on the row that misses it — that is the whole
    // reason pinning exists.
    expect(
      screen.getByText(/Only 1 of 2 supporting post-mortems — pin it to override/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Reaching the Coach: 1 of 2 shown/)).toBeInTheDocument();
  });

  it("pins an under-supported lesson", async () => {
    api = mockApi({
      "GET /api/lessons/": [THIN],
      "PATCH /api/lessons/2/": { ...THIN, pinned: true, visible_to_coach: true },
    });
    renderWithProviders(<LessonsPage />);

    await waitFor(() =>
      expect(screen.getByText(/first 5-minute candle/)).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("button", { name: "Pin" }));

    await waitFor(() => {
      const patch = api.calls.find((c) => c.method === "PATCH");
      expect(patch?.body).toEqual({ pinned: true });
    });
  });

  it("writes a hand-authored lesson pinned, since it has no evidence", async () => {
    api = mockApi({
      "GET /api/lessons/": [],
      "POST /api/lessons/": { ...THIN, id: 3, pinned: true, visible_to_coach: true },
    });
    renderWithProviders(<LessonsPage />);

    await waitFor(() => expect(screen.getByText("No lessons yet")).toBeInTheDocument());
    await userEvent.type(screen.getByLabelText("Lesson"), "Size down after two losses.");
    await userEvent.click(screen.getByRole("checkbox", { name: "bearish" }));
    await userEvent.click(screen.getByRole("button", { name: "Add lesson" }));

    await waitFor(() => {
      const post = api.calls.find((c) => c.method === "POST");
      expect(post?.body).toEqual({
        text: "Size down after two losses.",
        tags: { directions: ["bearish"], sectors: [] },
        pinned: true,
      });
    });
  });

  it("passes the visibility filter through to the endpoint", async () => {
    api = mockApi({ "GET /api/lessons/": [SUPPORTED] });
    renderWithProviders(<LessonsPage />);

    await waitFor(() => expect(screen.getByText(/I add to losers/)).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Coach visibility"), "no");

    await waitFor(() =>
      expect(api.calls.some((c) => c.url.includes("visible=false"))).toBe(true),
    );
  });

  it("will not delete a hand-written lesson without asking, and quotes it", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    api = mockApi({ "GET /api/lessons/": [THIN] });
    renderWithProviders(<LessonsPage />);

    await waitFor(() => expect(screen.getByText(/first 5-minute candle/)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    const message = String(confirmSpy.mock.calls[0]?.[0]);
    expect(message).toContain(THIN.text);
    // support_n = 1 here, so the prompt promises regeneration rather than permanence.
    expect(message).toMatch(/distilled from 1 post-mortem,/);
    expect(api.calls.some((c) => c.method === "DELETE")).toBe(false);
  });

  it("warns that a lesson with no supporting post-mortems is the only copy", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const handWritten = { ...THIN, id: 4, support_n: 0, pinned: true, text: "Stop revenge trading." };
    api = mockApi({
      "GET /api/lessons/": [handWritten],
      "DELETE /api/lessons/4/": {},
    });
    renderWithProviders(<LessonsPage />);

    await waitFor(() => expect(screen.getByText(/Stop revenge trading/)).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Delete" }));

    expect(String(confirmSpy.mock.calls[0]?.[0])).toMatch(/nothing regenerates it/);
    await waitFor(() =>
      expect(api.calls.some((c) => c.method === "DELETE")).toBe(true),
    );
  });
});
