import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import NewsFeed from "../components/NewsFeed";

const ITEMS = [
  { id: 1, headline: "Older", source: "R", summary: "", url: "https://x/1", datetime: 1000 },
  { id: 2, headline: "Newer", source: "B", summary: "Sub", url: "https://x/2", datetime: 2000 },
];

describe("NewsFeed", () => {
  it("renders newest first and links headlines", () => {
    render(<NewsFeed items={ITEMS} />);
    const headlines = screen.getAllByRole("link").map((a) => a.textContent);
    expect(headlines[0]).toBe("Newer");
    expect(headlines[1]).toBe("Older");
  });

  it("shows empty state with no items", () => {
    render(<NewsFeed items={[]} />);
    expect(screen.getByText(/no headlines/i)).toBeInTheDocument();
  });
});
