import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type React from "react";
import { SkeletonRows } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";
import { ErrorBoundary } from "../components/ErrorBoundary";

describe("Skeleton", () => {

  it("SkeletonRows renders N rows", () => {
    render(<SkeletonRows rows={3} />);
    const rows = document.querySelectorAll('[data-testid="skeleton-row"]');
    expect(rows.length).toBe(3);
  });
});

describe("EmptyState", () => {
  it("renders title + body + optional action", () => {
    render(
      <EmptyState
        title="No triggers yet"
        body="Create one to watch the market"
        action={<button>Create</button>}
      />,
    );
    expect(screen.getByText("No triggers yet")).toBeInTheDocument();
    expect(screen.getByText("Create one to watch the market")).toBeInTheDocument();
    expect(screen.getByText("Create")).toBeInTheDocument();
  });
});

function Boom(): React.ReactNode {
  throw new Error("crash");
}

describe("ErrorBoundary", () => {
  it("renders fallback when child throws", () => {
    // Silence the expected console.error from React
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    try {
      render(
        <ErrorBoundary>
          <Boom />
        </ErrorBoundary>,
      );
      expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
      expect(screen.getByText("crash")).toBeInTheDocument();
    } finally {
      spy.mockRestore();
    }
  });
});
