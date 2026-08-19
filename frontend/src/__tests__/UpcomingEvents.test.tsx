import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { useUpcomingEvents } from "@/hooks/useUpcomingEvents";
import UpcomingEvents from "@/components/UpcomingEvents";

vi.mock("@/hooks/useUpcomingEvents", () => ({
  useUpcomingEvents: vi.fn(),
}));

const mockUseUpcomingEvents = vi.mocked(useUpcomingEvents);

function renderComponent(tickers: string[] = []) {
  return render(
    <MemoryRouter>
      <UpcomingEvents tickers={tickers} />
    </MemoryRouter>,
  );
}

describe("UpcomingEvents", () => {
  beforeEach(() => {
    mockUseUpcomingEvents.mockReturnValue({
      data: undefined,
      isLoading: false,
      isSuccess: false,
      isError: false,
    } as unknown as ReturnType<typeof useUpcomingEvents>);
  });

  it("renders nothing when there are no events", () => {
    mockUseUpcomingEvents.mockReturnValue({
      data: { earnings: [], macro: [] },
      isLoading: false,
      isSuccess: true,
      isError: false,
    } as unknown as ReturnType<typeof useUpcomingEvents>);
    const { container } = renderComponent();
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when data is undefined", () => {
    const { container } = renderComponent();
    expect(container.firstChild).toBeNull();
  });

  it("renders a chip with ticker earnings label and days_until for an earnings event", () => {
    mockUseUpcomingEvents.mockReturnValue({
      data: {
        earnings: [
          {
            kind: "earnings",
            ticker: "AAPL",
            title: "AAPL earnings",
            event_time: "2026-06-01T20:00:00Z",
            days_until: 5,
            when_hint: "amc",
            impact: "high",
            detail: {},
          },
        ],
        macro: [],
      },
      isLoading: false,
      isSuccess: true,
      isError: false,
    } as unknown as ReturnType<typeof useUpcomingEvents>);

    renderComponent(["AAPL"]);

    const link = screen.getByRole("link");
    expect(link).toBeInTheDocument();
    expect(link.textContent).toContain("AAPL earnings");
    expect(link.textContent).toContain("5d");
    expect(link).toHaveAttribute("href", "/events");
  });

  it("renders a chip with title and days_until for a macro event (no ticker)", () => {
    mockUseUpcomingEvents.mockReturnValue({
      data: {
        earnings: [],
        macro: [
          {
            kind: "macro",
            ticker: "",
            title: "CPI Report",
            event_time: "2026-06-03T12:30:00Z",
            days_until: 7,
            when_hint: "",
            impact: "high",
            detail: {},
          },
        ],
      },
      isLoading: false,
      isSuccess: true,
      isError: false,
    } as unknown as ReturnType<typeof useUpcomingEvents>);

    renderComponent();

    const link = screen.getByRole("link");
    expect(link.textContent).toContain("CPI Report");
    expect(link.textContent).toContain("7d");
    expect(link).toHaveAttribute("href", "/events");
  });

  it("shows at most 2 chips sorted by days_until ascending", () => {
    mockUseUpcomingEvents.mockReturnValue({
      data: {
        earnings: [
          {
            kind: "earnings",
            ticker: "MSFT",
            title: "MSFT earnings",
            event_time: "2026-06-05T20:00:00Z",
            days_until: 9,
            when_hint: "amc",
            impact: "high",
            detail: {},
          },
          {
            kind: "earnings",
            ticker: "NVDA",
            title: "NVDA earnings",
            event_time: "2026-06-02T20:00:00Z",
            days_until: 3,
            when_hint: "amc",
            impact: "high",
            detail: {},
          },
        ],
        macro: [
          {
            kind: "macro",
            ticker: "",
            title: "PPI Release",
            event_time: "2026-06-10T12:30:00Z",
            days_until: 14,
            when_hint: "",
            impact: "medium",
            detail: {},
          },
        ],
      },
      isLoading: false,
      isSuccess: true,
      isError: false,
    } as unknown as ReturnType<typeof useUpcomingEvents>);

    renderComponent(["MSFT", "NVDA"]);

    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0].textContent).toContain("NVDA earnings");
    expect(links[0].textContent).toContain("3d");
    expect(links[1].textContent).toContain("MSFT earnings");
    expect(links[1].textContent).toContain("9d");
  });
});
