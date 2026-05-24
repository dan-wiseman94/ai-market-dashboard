import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./testUtils";
import WatchlistDetail from "@/pages/WatchlistDetail";
import type { Watchlist } from "@/api/watchlists";

vi.mock("@/hooks/useWatchlist", () => ({
  useWatchlist: vi.fn(),
  useAddSymbol: vi.fn(),
  useRemoveSymbol: vi.fn(),
}));

vi.mock("@/hooks/useQuotes", () => ({
  useQuotes: vi.fn(() => ({ data: {} })),
}));

import {
  useWatchlist,
  useAddSymbol,
  useRemoveSymbol,
} from "@/hooks/useWatchlist";

const mockUseWatchlist = vi.mocked(useWatchlist);
const mockUseAddSymbol = vi.mocked(useAddSymbol);
const mockUseRemoveSymbol = vi.mocked(useRemoveSymbol);

const WATCHLIST: Watchlist = {
  id: 42,
  name: "Tech Watchlist",
  created_at: "2026-01-01T00:00:00Z",
  symbols: [
    { id: 1, ticker: "AAPL", sort_order: 0 },
    { id: 2, ticker: "MSFT", sort_order: 1 },
  ],
};

function makeAdd(impl?: (ticker: string, opts?: { onSuccess?: () => void }) => void) {
  const mockMutate = vi.fn();
  mockMutate.mockImplementation(impl ?? ((_ticker, opts) => opts?.onSuccess?.()));
  mockUseAddSymbol.mockReturnValue({ mutate: mockMutate, isError: false, error: null, isPending: false } as never);
  return mockMutate;
}

function makeRemove() {
  const mockMutate = vi.fn();
  mockUseRemoveSymbol.mockReturnValue({ mutate: mockMutate, isPending: false } as never);
  return mockMutate;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseWatchlist.mockReturnValue({ data: WATCHLIST, isLoading: false } as never);
  makeAdd();
  makeRemove();
});

function renderDetail(id = "42") {
  return renderWithProviders(<WatchlistDetail />, {
    initialEntries: [`/watchlists/${id}`],
    routePath: "/watchlists/:id",
  });
}

describe("WatchlistDetail", () => {
  it("shows 'Invalid watchlist' when no id param resolves", () => {
    // render without a matching route param
    renderWithProviders(<WatchlistDetail />, {
      initialEntries: ["/watchlists/"],
      routePath: "/watchlists/",
    });
    expect(screen.getByText("Invalid watchlist")).toBeInTheDocument();
  });

  it("shows loading state when isLoading is true", () => {
    mockUseWatchlist.mockReturnValue({ data: undefined, isLoading: true } as never);
    renderDetail();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders watchlist name as h1 when loaded", () => {
    renderDetail();
    expect(screen.getByRole("heading", { level: 1, name: "Tech Watchlist" })).toBeInTheDocument();
  });

  it("add ticker: type ticker, submit form, calls add.mutate with uppercased ticker", async () => {
    const addMutate = vi.fn();
    mockUseAddSymbol.mockReturnValue({ mutate: addMutate, isError: false, error: null, isPending: false } as never);

    const user = userEvent.setup();
    renderDetail();

    await user.type(screen.getByPlaceholderText(/add ticker/i), "spy");
    fireEvent.click(screen.getByRole("button", { name: /add/i }));

    expect(addMutate).toHaveBeenCalledOnce();
    const [ticker] = addMutate.mock.calls[0];
    expect(ticker).toBe("SPY");
  });

  it("empty ticker submit does not call mutate", () => {
    const addMutate = vi.fn();
    mockUseAddSymbol.mockReturnValue({ mutate: addMutate, isError: false, error: null, isPending: false } as never);

    renderDetail();
    fireEvent.click(screen.getByRole("button", { name: /add/i }));
    expect(addMutate).not.toHaveBeenCalled();
  });

  it("shows error message when add.isError is true", () => {
    mockUseAddSymbol.mockReturnValue({
      mutate: vi.fn(),
      isError: true,
      error: new Error("Symbol not found"),
      isPending: false,
    } as never);

    renderDetail();
    expect(screen.getByText("Symbol not found")).toBeInTheDocument();
  });

  it("renders WatchlistTable with symbols", () => {
    renderDetail();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });

  it("WatchlistTable onRemove is wired to remove.mutate", async () => {
    const removeMutate = vi.fn();
    mockUseRemoveSymbol.mockReturnValue({ mutate: removeMutate, isPending: false } as never);

    const user = userEvent.setup();
    renderDetail();

    const removeButtons = screen.getAllByRole("button", { name: /remove/i });
    await user.click(removeButtons[0]);
    expect(removeMutate).toHaveBeenCalledWith(WATCHLIST.symbols[0].id);
  });

  it("after add succeeds, ticker input is cleared", async () => {
    const addMutate = vi.fn().mockImplementation((_ticker, opts) => opts?.onSuccess?.());
    mockUseAddSymbol.mockReturnValue({ mutate: addMutate, isError: false, error: null, isPending: false } as never);

    const user = userEvent.setup();
    renderDetail();

    const tickerInput = screen.getByPlaceholderText(/add ticker/i);
    await user.type(tickerInput, "GOOG");
    fireEvent.click(screen.getByRole("button", { name: /add/i }));

    await waitFor(() => expect(tickerInput).toHaveValue(""));
  });
});
