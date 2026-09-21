import { screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FileAttachPanel } from "../components/FileAttachPanel";
import type { UserFile } from "@/hooks/useFiles";
import { renderWithProviders } from "./testUtils";

const FILES: UserFile[] = [
  { id: 1, filename: "10k.pdf", kind: "filing", ticker: "AAPL", mime: "application/pdf", size: 123 },
  { id: 2, filename: "q3.txt", kind: "transcript", ticker: "AAPL", mime: "text/plain", size: 456 },
];

describe("FileAttachPanel", () => {
  it("renders empty state when no files", () => {
    renderWithProviders(
      <FileAttachPanel threadId={1} files={[]} onAttach={vi.fn()} />,
    );
    expect(screen.getByText(/no files/i)).toBeInTheDocument();
  });

  it("renders a list of files with an Attach button per row", () => {
    const onAttach = vi.fn();
    renderWithProviders(
      <FileAttachPanel threadId={7} files={FILES} onAttach={onAttach} />,
    );
    expect(screen.getByText("10k.pdf")).toBeInTheDocument();
    expect(screen.getByText("q3.txt")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: /attach/i });
    expect(buttons.length).toBe(2);
    fireEvent.click(buttons[0]);
    expect(onAttach).toHaveBeenCalledWith(1);
  });

  it("offers no delete control when onDelete is omitted", () => {
    renderWithProviders(
      <FileAttachPanel threadId={7} files={FILES} onAttach={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });

  it("names the delete control per row and hands back the whole file", () => {
    const onDelete = vi.fn();
    renderWithProviders(
      <FileAttachPanel threadId={7} files={FILES} onAttach={vi.fn()} onDelete={onDelete} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete q3.txt" }));
    expect(onDelete).toHaveBeenCalledWith(FILES[1]);
  });

  it("disables attach — and says why — when the provider can't read documents", () => {
    const onAttach = vi.fn();
    renderWithProviders(
      <FileAttachPanel
        threadId={7}
        files={FILES}
        onAttach={onAttach}
        attachDisabledReason="Files are Claude-only."
      />,
    );
    const attach = screen.getByRole("button", { name: "Attach 10k.pdf" });
    expect(attach).toBeDisabled();
    expect(attach).toHaveAttribute("title", "Files are Claude-only.");
    fireEvent.click(attach);
    expect(onAttach).not.toHaveBeenCalled();
  });
});
