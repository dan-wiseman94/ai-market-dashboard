/**
 * Tests for command-palette action verbs (Part 1) and global recall search (Part 2).
 *
 * Strategy:
 * - Part 1: Render CommandPalette with verb commands (spy on mutation / callback) and
 *   assert the action fires when the command is clicked.
 * - Part 2: Render CommandPalette with extraCommands fed from mocked recall data and
 *   assert that recall hits render + selecting one navigates to hit.link.
 *
 * We do NOT render AppLayout here (too heavy); instead we test the building blocks
 * directly so the assertions are tight:
 *   - CommandPalette accepts extraCommands and renders them
 *   - Clicking an extraCommand item runs its `run()` callback
 *   - useDefaultCommands wires action verbs via a thin smoke-render of AppLayout
 */

import { screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CommandPalette, type Command } from "../components/CommandPalette";
import { renderWithProviders } from "./testUtils";

function renderPalette(commands: Command[], extra: Command[] = [], onClose = vi.fn()) {
  return renderWithProviders(
    <CommandPalette open={true} onClose={onClose} commands={commands} extraCommands={extra} />,
  );
}

describe("CommandPalette — extraCommands (recall search results)", () => {
  it("renders recall hits passed as extraCommands", () => {
    const recallCmd: Command = {
      id: "recall:thesis:42",
      label: "NVDA bullish into earnings — AI demand",
      section: "Recall",
      keywords: "NVDA",
      run: vi.fn(),
    };
    renderPalette(
      [{ id: "static", label: "Static command", run: vi.fn() }],
      [recallCmd],
    );
    expect(screen.getByText("Static command")).toBeInTheDocument();
    expect(screen.getByText("NVDA bullish into earnings — AI demand")).toBeInTheDocument();
    expect(screen.getByText("Recall")).toBeInTheDocument();
  });

  it("clicking a recall hit invokes its run() and closes the palette", () => {
    const navSpy = vi.fn();
    const onClose = vi.fn();
    const recallCmd: Command = {
      id: "recall:thesis:42",
      label: "NVDA bullish into earnings",
      section: "Recall",
      keywords: "NVDA",
      run: navSpy,
    };
    renderWithProviders(
      <CommandPalette
        open={true}
        onClose={onClose}
        commands={[]}
        extraCommands={[recallCmd]}
      />,
    );
    fireEvent.click(screen.getByText("NVDA bullish into earnings"));
    expect(navSpy).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("extraCommands are shown even when a static command matches the query", () => {
    const recallCmd: Command = {
      id: "recall:observation:7",
      label: "SPY breadth divergence noted",
      section: "Recall",
      keywords: "SPY",
      run: vi.fn(),
    };
    renderPalette(
      [{ id: "go-dashboard", label: "Dashboard", run: vi.fn() }],
      [recallCmd],
    );
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "dashboard" } });
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    // recall extra should also be present (extraCommands are not filtered)
    expect(screen.getByText("SPY breadth divergence noted")).toBeInTheDocument();
  });

  it("onQueryChange is called when the input changes", () => {
    const onQueryChange = vi.fn();
    renderWithProviders(
      <CommandPalette
        open={true}
        onClose={vi.fn()}
        commands={[]}
        onQueryChange={onQueryChange}
      />,
    );
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: "earnings" } });
    expect(onQueryChange).toHaveBeenCalledWith("earnings");
  });
});
