import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./testUtils";
import WatchlistsList from "@/pages/WatchlistsList";
import type { Watchlist } from "@/api/watchlists";

vi.mock("@/hooks/useWatchlists", () => ({
  useWatchlists: vi.fn(),
  useCreateWatchlist: vi.fn(),
  useDeleteWatchlist: vi.fn(),
}));

import {
  useWatchlists,
  useCreateWatchlist,
  useDeleteWatchlist,
} from "@/hooks/useWatchlists";

const mockUseWatchlists = vi.mocked(useWatchlists);
const mockUseCreateWatchlist = vi.mocked(useCreateWatchlist);
const mockUseDeleteWatchlist = vi.mocked(useDeleteWatchlist);

const WATCHLIST_A: Watchlist = {
  id: 1,
  name: "My Tech Picks",
  created_at: "2026-01-01T00:00:00Z",
  symbols: [
    { id: 1, ticker: "AAPL", sort_order: 0 },
    { id: 2, ticker: "MSFT", sort_order: 1 },
  ],
};

const WATCHLIST_B: Watchlist = {
  id: 2,
  name: "ETFs",
  created_at: "2026-01-02T00:00:00Z",
  symbols: [],
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

beforeEach(() => {
  vi.clearAllMocks();
  mockUseWatchlists.mockReturnValue({ data: [WATCHLIST_A, WATCHLIST_B], isLoading: false } as never);
  makeCreate();
  makeDelete();
});

describe("WatchlistsList", () => {
  it("renders loading state", () => {
    mockUseWatchlists.mockReturnValue({ data: undefined, isLoading: true } as never);
    renderWithProviders(<WatchlistsList />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
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

    const deleteButtons = screen.getAllByRole("button", { name: /delete/i });
    await user.click(deleteButtons[0]);
    expect(delMutate).toHaveBeenCalledWith(WATCHLIST_A.id);
  });
});
