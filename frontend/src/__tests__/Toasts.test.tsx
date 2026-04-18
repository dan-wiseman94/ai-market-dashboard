import { render, screen, act, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ToastProvider, useToast } from "../hooks/useToast";
import { Toasts } from "../components/Toasts";

function Fixture() {
  const { push } = useToast();
  return (
    <button onClick={() => push({ kind: "success", text: "saved!" })}>go</button>
  );
}

describe("Toasts", () => {
  it("renders a toast when push() is called", () => {
    render(
      <ToastProvider>
        <Toasts />
        <Fixture />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("go"));
    expect(screen.getByText("saved!")).toBeInTheDocument();
  });

  it("auto-dismisses after the configured duration", () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider defaultDurationMs={1000}>
          <Toasts />
          <Fixture />
        </ToastProvider>,
      );
      fireEvent.click(screen.getByText("go"));
      expect(screen.getByText("saved!")).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(1001);
      });
      expect(screen.queryByText("saved!")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("click dismisses immediately", () => {
    render(
      <ToastProvider>
        <Toasts />
        <Fixture />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText("go"));
    const toast = screen.getByText("saved!");
    fireEvent.click(toast);
    expect(screen.queryByText("saved!")).not.toBeInTheDocument();
  });
});
