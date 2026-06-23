import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { useThreadsPage } from "@/hooks/useThread";
import ThreadsPage from "@/pages/ThreadsPage";

vi.mock("@/hooks/useThread", () => ({ useThreadsPage: vi.fn() }));

const ROWS = [
  { id: 1, kind: "consult", title: "NVDA earnings", profile: { name: "Swing" }, created_at: new Date().toISOString(), message_count: 2, pinned_snapshot_id: null },
  { id: 2, kind: "chat", title: "Macro check", profile: { name: "Macro" }, created_at: new Date().toISOString(), message_count: 1, pinned_snapshot_id: null },
];

function setup(count: number) {
  vi.mocked(useThreadsPage).mockReturnValue({
    data: { results: ROWS, count, next: null, previous: null },
    isLoading: false,
  } as ReturnType<typeof useThreadsPage>);
  return render(
    <MemoryRouter>
      <ThreadsPage />
    </MemoryRouter>,
  );
}

describe("ThreadsPage", () => {
  it("filters the loaded page by the Filter input", () => {
    setup(2);
    expect(screen.getByTestId("thread-row-1")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "macro" } });
    expect(screen.queryByTestId("thread-row-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("thread-row-2")).toBeInTheDocument();
  });

  it("shows pagination only when there is more than one page", () => {
    const { unmount } = setup(2);
    expect(screen.queryByRole("button", { name: "Next" })).not.toBeInTheDocument();
    unmount();
    setup(120);
    expect(screen.getByRole("button", { name: "Next" })).toBeInTheDocument();
    expect(screen.getByText("1–50 of 120")).toBeInTheDocument();
  });
});
