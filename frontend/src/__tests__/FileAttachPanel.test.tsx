import { screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FileAttachPanel } from "../components/FileAttachPanel";
import { renderWithProviders } from "./testUtils";

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
      <FileAttachPanel
        threadId={7}
        files={[
          { id: 1, filename: "10k.pdf", kind: "filing", ticker: "AAPL",
             mime: "application/pdf", size: 123 },
          { id: 2, filename: "q3.txt", kind: "transcript", ticker: "AAPL",
             mime: "text/plain", size: 456 },
        ]}
        onAttach={onAttach}
      />,
    );
    expect(screen.getByText("10k.pdf")).toBeInTheDocument();
    expect(screen.getByText("q3.txt")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button", { name: /attach/i });
    expect(buttons.length).toBe(2);
    fireEvent.click(buttons[0]);
    expect(onAttach).toHaveBeenCalledWith(1);
  });
});
