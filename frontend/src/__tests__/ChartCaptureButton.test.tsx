import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChartCaptureButton from "../components/ChartCaptureButton";
import { mockFetch } from "./testUtils";

const fakePng = new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: "image/png" });

vi.mock("html2canvas", () => ({
  default: vi.fn(() =>
    Promise.resolve({
      toBlob: (cb: (b: Blob) => void) => cb(fakePng),
    }),
  ),
}));

beforeEach(() => {
  localStorage.clear();
  mockFetch(() => ({ ok: true, status: 201, json: () => Promise.resolve({ id: 42 }) }));
});

describe("ChartCaptureButton", () => {
  it("captures the chart, posts the PNG, and stores the staged image id", async () => {
    const targetRef = { current: document.createElement("div") };
    render(<ChartCaptureButton targetRef={targetRef} caption="SPY 5m" />);
    fireEvent.click(screen.getByRole("button", { name: /capture/i }));

    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("staged_image_ids") || "[]");
      expect(stored).toEqual([42]);
    });
    expect(globalThis.fetch).toHaveBeenCalledWith(
      "/api/snapshots/images/?staged=true",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
