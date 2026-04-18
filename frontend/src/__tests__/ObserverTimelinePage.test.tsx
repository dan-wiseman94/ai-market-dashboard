import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ObserverTimelinePage from "../pages/ObserverTimelinePage";

const FAKE_THREAD = {
  id: 7, kind: "observer", profile_id: 1, title: "Observer: P",
  messages: [
    { id: 1, role: "user", content: { text: "Snapshot 1" }, created_at: "2026-04-17T09:35:00Z" },
    { id: 2, role: "assistant", content: { text: "AI response 1" }, created_at: "2026-04-17T09:35:05Z" },
  ],
};

beforeEach(() => {
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve(FAKE_THREAD) }),
  ) as never;
});

const qc = () => new QueryClient({ defaultOptions: { queries: { retry: false } } });

describe("ObserverTimelinePage", () => {
  it("renders messages, expands on click", async () => {
    render(
      <QueryClientProvider client={qc()}>
        <MemoryRouter initialEntries={["/threads/observer/1"]}>
          <Routes>
            <Route path="/threads/observer/:profileId" element={<ObserverTimelinePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => expect(screen.getByText(/Observer: P/)).toBeInTheDocument());
    const headers = screen.getAllByRole("button", { name: /(snapshot|response)/i });
    expect(headers.length).toBeGreaterThan(0);
    fireEvent.click(headers[0]);
    expect(screen.getByText(/AI response 1/i)).toBeInTheDocument();
  });
});
