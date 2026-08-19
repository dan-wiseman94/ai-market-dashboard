import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SaveCardButton } from "../components/SaveCardButton";

// Mirror ChartCaptureButton's test-mock approach: mock html2canvas as a
// dynamic import (the module returns a default export that is a function).
vi.mock("html2canvas", () => ({
  default: vi.fn(() =>
    Promise.resolve({
      toDataURL: (_type: string) => "data:image/png;base64,fakedata",
    }),
  ),
}));

describe("SaveCardButton", () => {
  let clickSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(async () => {
    // Spy on anchor click so we can verify a download was triggered.
    // mockRestore first in case a previous test left it patched.
    clickSpy?.mockRestore();
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  it("calls html2canvas with the target element and triggers a download", async () => {
    const div = document.createElement("div");
    const targetRef = { current: div };

    render(<SaveCardButton targetRef={targetRef} filename="test-card.png" />);

    fireEvent.click(screen.getByRole("button", { name: /save image/i }));

    await waitFor(() => {
      expect(clickSpy).toHaveBeenCalled();
    });

    const html2canvas = (await import("html2canvas")).default;
    expect(html2canvas).toHaveBeenCalledWith(div);
  });

  it("sets the download filename on the anchor", async () => {
    const div = document.createElement("div");
    const targetRef = { current: div };

    let capturedAnchor: HTMLAnchorElement | null = null;
    const createElementOrig = document.createElement.bind(document);
    const createElSpy = vi
      .spyOn(document, "createElement")
      .mockImplementation((tag: string) => {
        const el = createElementOrig(tag);
        if (tag === "a") capturedAnchor = el as HTMLAnchorElement;
        return el;
      });

    render(
      <SaveCardButton targetRef={targetRef} filename="observation-bullish-2026.png" />,
    );

    fireEvent.click(screen.getByRole("button", { name: /save image/i }));

    await waitFor(() => {
      expect(capturedAnchor?.download).toBe("observation-bullish-2026.png");
    });

    createElSpy.mockRestore();
  });

  it("does nothing when targetRef.current is null (no crash, html2canvas not called)", async () => {
    const targetRef = { current: null };

    const html2canvas = (await import("html2canvas")).default as ReturnType<typeof vi.fn>;
    html2canvas.mockClear();

    render(<SaveCardButton targetRef={targetRef} filename="observation.png" />);

    fireEvent.click(screen.getByRole("button", { name: /save image/i }));

    // Give any async path a chance to run
    await new Promise((r) => setTimeout(r, 50));

    expect(html2canvas).not.toHaveBeenCalled();
    expect(clickSpy).not.toHaveBeenCalled();
  });

  it("renders a custom label", () => {
    const targetRef = { current: document.createElement("div") };
    render(<SaveCardButton targetRef={targetRef} filename="x.png" label="Export card" />);
    expect(screen.getByRole("button", { name: /export card/i })).toBeInTheDocument();
  });
});
