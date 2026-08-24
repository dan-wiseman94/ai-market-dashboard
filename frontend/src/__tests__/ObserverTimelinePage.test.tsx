import { describe, it, expect, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { mockApi, renderWithProviders } from "./testUtils";
import ObserverTimelinePage from "../pages/ObserverTimelinePage";

const FAKE_THREAD = {
  id: 7, kind: "observer", profile_id: 1, title: "Observer: P",
  messages: [
    { id: 1, role: "user", content: { text: "Snapshot 1" }, created_at: "2026-04-17T09:35:00Z" },
    { id: 2, role: "assistant", content: { text: "AI response 1" }, created_at: "2026-04-17T09:35:05Z" },
  ],
};

beforeEach(() => {
  mockApi({ "GET /api/observer/threads/1/": FAKE_THREAD });
});

describe("ObserverTimelinePage", () => {
  it("renders messages, expands on click", async () => {
    renderWithProviders(<ObserverTimelinePage />, {
      initialEntries: ["/threads/observer/1"],
      routePath: "/threads/observer/:profileId",
    });

    await waitFor(() => expect(screen.getByText(/Observer: P/)).toBeInTheDocument());
    const headers = screen.getAllByRole("button", { name: /(snapshot|response)/i });
    expect(headers.length).toBeGreaterThan(0);
    fireEvent.click(headers[0]);
    expect(screen.getByText(/AI response 1/i)).toBeInTheDocument();
  });
});
