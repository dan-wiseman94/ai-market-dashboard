import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { CommandPalette } from "../components/CommandPalette";

function Wrap({ open, onClose = vi.fn() }: { open: boolean; onClose?: () => void }) {
  const commands = [
    { id: "dash", label: "Dashboard", keywords: "home", run: vi.fn() },
    { id: "trig", label: "Triggers", keywords: "alerts", run: vi.fn() },
  ];
  return (
    <MemoryRouter>
      <CommandPalette open={open} onClose={onClose} commands={commands} />
    </MemoryRouter>
  );
}

describe("CommandPalette", () => {
  it("renders commands when open", () => {
    render(<Wrap open={true} />);
    expect(screen.getByText("Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Triggers")).toBeInTheDocument();
  });

  it("filters by query substring on label", () => {
    render(<Wrap open={true} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "trig" },
    });
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
    expect(screen.getByText("Triggers")).toBeInTheDocument();
  });

  it("filters by keywords", () => {
    render(<Wrap open={true} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "alerts" },
    });
    expect(screen.getByText("Triggers")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(<Wrap open={false} />);
    expect(screen.queryByText("Dashboard")).not.toBeInTheDocument();
  });

  it("Escape closes", () => {
    const onClose = vi.fn();
    render(<Wrap open={true} onClose={onClose} />);
    const input = screen.getByPlaceholderText(/search/i);
    fireEvent.keyDown(input.parentElement!, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("shows 'no match' when filter empties the list", () => {
    render(<Wrap open={true} />);
    fireEvent.change(screen.getByPlaceholderText(/search/i), {
      target: { value: "zzzzz" },
    });
    expect(screen.getByText(/no commands match/i)).toBeInTheDocument();
  });
});
