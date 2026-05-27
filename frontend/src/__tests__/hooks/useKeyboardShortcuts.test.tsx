import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import {
  useCommandPaletteTrigger,
  useKeyboardShortcuts,
} from "@/hooks/useKeyboardShortcuts";

function NavHarness({ onHelp = () => {} }: { onHelp?: () => void }) {
  useKeyboardShortcuts(onHelp);
  const loc = useLocation();
  return (
    <>
      <input data-testid="inp" />
      <div data-testid="path">{loc.pathname}</div>
    </>
  );
}

function renderNav(onHelp?: () => void) {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <NavHarness onHelp={onHelp} />
    </MemoryRouter>,
  );
  return () => screen.getByTestId("path").textContent;
}

describe("useKeyboardShortcuts (g-chord navigation)", () => {
  afterEach(() => vi.useRealTimers());

  it("navigates to the mapped route after the g prefix", () => {
    const path = renderNav();
    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "t" });
    expect(path()).toBe("/triggers");
  });

  it("is case-insensitive on the second key", () => {
    const path = renderNav();
    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "A" });
    expect(path()).toBe("/analytics");
  });

  it("does nothing for a nav key pressed without the g prefix", () => {
    const path = renderNav();
    fireEvent.keyDown(window, { key: "t" });
    expect(path()).toBe("/");
  });

  it("does not navigate when g is followed by an unmapped key", () => {
    const path = renderNav();
    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "z" });
    expect(path()).toBe("/");
  });

  it("calls the help callback on ?", () => {
    const onHelp = vi.fn();
    renderNav(onHelp);
    fireEvent.keyDown(window, { key: "?" });
    expect(onHelp).toHaveBeenCalledTimes(1);
  });

  it("ignores shortcuts while a text input is focused", () => {
    const path = renderNav();
    screen.getByTestId("inp").focus();
    fireEvent.keyDown(window, { key: "g" });
    fireEvent.keyDown(window, { key: "t" });
    expect(path()).toBe("/");
  });

  it("ignores the chord when a modifier is held", () => {
    const path = renderNav();
    fireEvent.keyDown(window, { key: "g", metaKey: true });
    fireEvent.keyDown(window, { key: "t" });
    expect(path()).toBe("/");
  });

  it("forgets the g prefix after the 800ms window lapses", () => {
    vi.useFakeTimers();
    const path = renderNav();
    fireEvent.keyDown(window, { key: "g" });
    act(() => vi.advanceTimersByTime(900));
    fireEvent.keyDown(window, { key: "t" });
    expect(path()).toBe("/");
  });
});

function PaletteHarness({ onOpen }: { onOpen: () => void }) {
  useCommandPaletteTrigger(onOpen);
  return null;
}

describe("useCommandPaletteTrigger (Cmd/Ctrl-K)", () => {
  it("opens on Cmd-K", () => {
    const onOpen = vi.fn();
    render(<PaletteHarness onOpen={onOpen} />);
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("opens on Ctrl-K", () => {
    const onOpen = vi.fn();
    render(<PaletteHarness onOpen={onOpen} />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("opens on Cmd-Shift-K (uppercase key)", () => {
    const onOpen = vi.fn();
    render(<PaletteHarness onOpen={onOpen} />);
    fireEvent.keyDown(window, { key: "K", metaKey: true });
    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it("does not open on a bare k", () => {
    const onOpen = vi.fn();
    render(<PaletteHarness onOpen={onOpen} />);
    fireEvent.keyDown(window, { key: "k" });
    expect(onOpen).not.toHaveBeenCalled();
  });

  it("does not open on Cmd with another key", () => {
    const onOpen = vi.fn();
    render(<PaletteHarness onOpen={onOpen} />);
    fireEvent.keyDown(window, { key: "j", metaKey: true });
    expect(onOpen).not.toHaveBeenCalled();
  });
});
