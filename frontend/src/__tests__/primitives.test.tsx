import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import type React from "react";
import { Skeleton, SkeletonRows } from "../components/Skeleton";
import { EmptyState } from "../components/EmptyState";
import { ErrorBoundary } from "../components/ErrorBoundary";

describe("Skeleton", () => {
  it("renders a pulse box", () => {
    const { container } = render(<Skeleton className="h-4 w-24" />);
    const box = container.firstChild as HTMLElement;
    expect(box.className).toContain("animate-pulse");
  });

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

  it("omits body and action when not provided", () => {
    render(<EmptyState title="Nothing here" />);
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
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

  it("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <div>ok</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("ok")).toBeInTheDocument();
  });
});
