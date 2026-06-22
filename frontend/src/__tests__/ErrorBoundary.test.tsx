import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "@/components/ErrorBoundary";

function Boom(): never {
  throw new Error("kaboom");
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("clears the caught error when resetKey changes (route nav recovers, no reload)", () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="/a">
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();

    // Navigating (resetKey changes) clears the trapped error and renders children.
    rerender(
      <ErrorBoundary resetKey="/b">
        <div>recovered</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("recovered")).toBeInTheDocument();
    expect(screen.queryByText("Something went wrong.")).not.toBeInTheDocument();
  });

  it("offers a Try again that clears the error in place", () => {
    let crash = true;
    function Maybe() {
      if (crash) throw new Error("x");
      return <div>ok now</div>;
    }
    const { rerender } = render(
      <ErrorBoundary>
        <Maybe />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
    crash = false;
    fireEvent.click(screen.getByText("Try again"));
    rerender(
      <ErrorBoundary>
        <Maybe />
      </ErrorBoundary>,
    );
    expect(screen.getByText("ok now")).toBeInTheDocument();
  });
});
