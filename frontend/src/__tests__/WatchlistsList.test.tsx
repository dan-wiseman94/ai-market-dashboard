import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./testUtils";
import WatchlistsList from "@/pages/WatchlistsList";
import type { Watchlist } from "@/api/watchlists";

vi.mock("@/hooks/useWatchlists", () => ({
  useWatchlists: vi.fn(),
  useCreateWatchlist: vi.fn(),
  useRenameWatchlist: vi.fn(),
  useDeleteWatchlist: vi.fn(),
}));

import {
  useWatchlists,
  useCreateWatchlist,
  useRenameWatchlist,
  useDeleteWatchlist,
} from "@/hooks/useWatchlists";

const mockUseWatchlists = vi.mocked(useWatchlists);
const mockUseCreateWatchlist = vi.mocked(useCreateWatchlist);
const mockUseRenameWatchlist = vi.mocked(useRenameWatchlist);
const mockUseDeleteWatchlist = vi.mocked(useDeleteWatchlist);

const WATCHLIST_A: Watchlist = {
  id: 1,
  name: "My Tech Picks",
  created_at: "2026-01-01T00:00:00Z",
  tickers: [
    { id: 1, ticker: "AAPL", sort_order: 0 },
    { id: 2, ticker: "MSFT", sort_order: 1 },
  ],
};

const WATCHLIST_B: Watchlist = {
  id: 2,
  name: "ETFs",
  created_at: "2026-01-02T00:00:00Z",
  tickers: [],
};

function makeCreate(impl?: (name: string, opts?: { onSuccess?: () => void }) => void) {
  const mockMutate = vi.fn();
  mockMutate.mockImplementation(impl ?? ((_name, opts) => opts?.onSuccess?.()));
  mockUseCreateWatchlist.mockReturnValue({ mutate: mockMutate, isPending: false } as never);
  return mockMutate;
}

function makeDelete() {
  const mockMutate = vi.fn();
  mockUseDeleteWatchlist.mockReturnValue({ mutate: mockMutate, isPending: false } as never);
  return mockMutate;
}

function makeRename() {
  const mockMutate = vi.fn();
  mockUseRenameWatchlist.mockReturnValue({ mutate: mockMutate, isPending: false } as never);
  return mockMutate;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseWatchlists.mockReturnValue({ data: [WATCHLIST_A, WATCHLIST_B], isLoading: false } as never);
  makeCreate();
  makeDelete();
  makeRename();
});

describe("WatchlistsList", () => {
  it("renders skeleton rows while loading", () => {
    mockUseWatchlists.mockReturnValue({ data: undefined, isLoading: true } as never);
    renderWithProviders(<WatchlistsList />);
    expect(screen.getAllByTestId("skeleton-row").length).toBeGreaterThan(0);
  });

  it("renders an empty state when there are no watchlists", () => {
    mockUseWatchlists.mockReturnValue({ data: [], isLoading: false } as never);
    renderWithProviders(<WatchlistsList />);
    expect(screen.getByText("No watchlists yet")).toBeInTheDocument();
  });

  it("renders one row per watchlist with symbol count", () => {
    renderWithProviders(<WatchlistsList />);
    expect(screen.getByTestId("watchlist-row-My Tech Picks")).toBeInTheDocument();
    expect(screen.getByText(/2 symbols/i)).toBeInTheDocument();
    expect(screen.getByTestId("watchlist-row-ETFs")).toBeInTheDocument();
    expect(screen.getByText(/0 symbols/i)).toBeInTheDocument();
  });

  it("create form: type name and submit calls create.mutate with the name", async () => {
    const createMutate = vi.fn();
    mockUseCreateWatchlist.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    const user = userEvent.setup();
    renderWithProviders(<WatchlistsList />);

    await user.type(screen.getByPlaceholderText(/new watchlist name/i), "Growth Stocks");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    expect(createMutate).toHaveBeenCalledOnce();
    const [name] = createMutate.mock.calls[0];
    expect(name).toBe("Growth Stocks");
  });

  it("onSuccess resets the name input to empty", async () => {
    const createMutate = vi.fn().mockImplementation((_name, opts) => opts?.onSuccess?.());
    mockUseCreateWatchlist.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    const user = userEvent.setup();
    renderWithProviders(<WatchlistsList />);

    const nameInput = screen.getByPlaceholderText(/new watchlist name/i);
    await user.type(nameInput, "Temp List");
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => expect(nameInput).toHaveValue(""));
  });

  it("empty name submit does not call mutate", () => {
    const createMutate = vi.fn();
    mockUseCreateWatchlist.mockReturnValue({ mutate: createMutate, isPending: false } as never);

    renderWithProviders(<WatchlistsList />);
    fireEvent.click(screen.getByRole("button", { name: /create/i }));
    expect(createMutate).not.toHaveBeenCalled();
  });

  it("Delete button calls del.mutate with the watchlist id", async () => {
    const delMutate = vi.fn();
    mockUseDeleteWatchlist.mockReturnValue({ mutate: delMutate, isPending: false } as never);

    const user = userEvent.setup();
    renderWithProviders(<WatchlistsList />);

    await user.click(screen.getByRole("button", { name: `Delete ${WATCHLIST_A.name}` }));
    expect(delMutate).toHaveBeenCalledWith(WATCHLIST_A.id);
  });

  it("inline rename: Rename opens an input and Save sends {id, name}", async () => {
    const renameMutate = makeRename();
    const user = userEvent.setup();
    renderWithProviders(<WatchlistsList />);

    await user.click(screen.getByRole("button", { name: `Rename ${WATCHLIST_A.name}` }));
    const input = screen.getByRole("textbox", { name: `New name for ${WATCHLIST_A.name}` });
    await user.clear(input);
    await user.type(input, "  Renamed list  ");
    await user.click(screen.getByRole("button", { name: `Save name for ${WATCHLIST_A.name}` }));

    expect(renameMutate).toHaveBeenCalledWith({ id: WATCHLIST_A.id, name: "Renamed list" });
  });

  it("inline rename: Escape abandons the edit without mutating", async () => {
    const renameMutate = makeRename();
    const user = userEvent.setup();
    renderWithProviders(<WatchlistsList />);

    await user.click(screen.getByRole("button", { name: `Rename ${WATCHLIST_A.name}` }));
    await user.type(
      screen.getByRole("textbox", { name: `New name for ${WATCHLIST_A.name}` }),
      "x{Escape}",
    );

    expect(renameMutate).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: `Rename ${WATCHLIST_A.name}` })).toBeInTheDocument();
  });

  it("inline rename: an unchanged name does not mutate", async () => {
    const renameMutate = makeRename();
    const user = userEvent.setup();
    renderWithProviders(<WatchlistsList />);

    await user.click(screen.getByRole("button", { name: `Rename ${WATCHLIST_B.name}` }));
    await user.click(screen.getByRole("button", { name: `Save name for ${WATCHLIST_B.name}` }));

    expect(renameMutate).not.toHaveBeenCalled();
  });

  it("each row's rename controls are distinguishable by watchlist name", async () => {
    const user = userEvent.setup();
    renderWithProviders(<WatchlistsList />);
    await user.click(screen.getByRole("button", { name: "Rename ETFs" }));
    // Only the ETFs row entered edit mode.
    expect(screen.getByRole("textbox", { name: "New name for ETFs" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: `Rename ${WATCHLIST_A.name}` }),
    ).toBeInTheDocument();
  });
});
