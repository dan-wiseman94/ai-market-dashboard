import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ErrorsPage from "@/pages/ErrorsPage";
import * as hooks from "@/hooks/useErrors";
import type { ErrorRow } from "@/hooks/useErrors";

const ERROR_ROWS: ErrorRow[] = [
  {
    id: 1,
    level: "error",
    source: "capture_task",
    message: "Connection timeout fetching quotes",
    fingerprint: "abc123",
    resolved: false,
    created_at: "2026-05-30T10:00:00Z",
  },
  {
    id: 2,
    level: "warning",
    source: "observer",
    message: "Retried after backoff",
    fingerprint: "def456",
    resolved: true,
    created_at: "2026-05-30T09:00:00Z",
  },
  {
    id: 3,
    level: "critical",
    source: "beat",
    message: "Celery beat heartbeat missed",
    fingerprint: "ghi789",
    resolved: false,
    created_at: "2026-05-30T08:00:00Z",
  },
];

function mockHooks(
  rows: ErrorRow[] = ERROR_ROWS,
  isLoading = false,
) {
  const mutateMock = vi.fn();
  vi.spyOn(hooks, "useErrors").mockReturnValue({
    data: { errors: rows, count: rows.length },
    isLoading,
    isSuccess: !isLoading,
  } as never);
  vi.spyOn(hooks, "useResolveError").mockReturnValue({
    mutate: mutateMock,
    isPending: false,
  } as never);
  return { mutateMock };
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ErrorsPage />
    </MemoryRouter>,
  );
}

describe("ErrorsPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders error rows with source, message, and level badge", async () => {
    mockHooks();
    renderPage();

    expect(screen.getByText("capture_task")).toBeInTheDocument();
    expect(
      screen.getByText("Connection timeout fetching quotes"),
    ).toBeInTheDocument();

    expect(screen.getByText("observer")).toBeInTheDocument();
    expect(screen.getByText("Retried after backoff")).toBeInTheDocument();

    expect(screen.getByText("beat")).toBeInTheDocument();
    expect(screen.getByText("Celery beat heartbeat missed")).toBeInTheDocument();

    expect(screen.getAllByText("error").length).toBeGreaterThan(0);
    expect(screen.getAllByText("warning").length).toBeGreaterThan(0);
    expect(screen.getAllByText("critical").length).toBeGreaterThan(0);
  });

  it("shows EmptyState when no errors", () => {
    mockHooks([]);
    renderPage();
    // EmptyState renders the title in an h3
    expect(
      screen.getByRole("heading", { name: /no errors/i }),
    ).toBeInTheDocument();
  });

  it("shows Skeleton rows while loading", () => {
    mockHooks([], true);
    renderPage();
    const skeletons = screen.getAllByTestId("skeleton-row");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("calls useErrors with unresolved=true when toggle is clicked", async () => {
    mockHooks();
    renderPage();

    const toggle = screen.getByRole("checkbox", { name: /unresolved only/i });
    await userEvent.click(toggle);

    expect(hooks.useErrors).toHaveBeenCalledWith(true);
  });

  it("clicking Resolve button calls the mutation with the row id", async () => {
    const { mutateMock } = mockHooks();
    renderPage();

    // Click the first Resolve button (for id=1 — unresolved row)
    const resolveButtons = screen.getAllByRole("button", { name: /resolve/i });
    expect(resolveButtons.length).toBeGreaterThan(0);
    await userEvent.click(resolveButtons[0]);

    expect(mutateMock).toHaveBeenCalledWith(expect.any(Number));
  });

  it("Resolve button is disabled for already-resolved rows", () => {
    mockHooks();
    renderPage();

    // Row id=2 is resolved=true; its button should be disabled
    // We check that at least one resolve button is disabled
    const allButtons = screen.getAllByRole("button", { name: /resolve/i });
    const disabledOnes = allButtons.filter((b) =>
      b.hasAttribute("disabled"),
    );
    expect(disabledOnes.length).toBeGreaterThan(0);
  });

  it("renders the page heading", () => {
    mockHooks();
    renderPage();
    expect(
      screen.getByRole("heading", { name: /errors/i }),
    ).toBeInTheDocument();
  });
});
