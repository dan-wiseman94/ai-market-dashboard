import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import ChartCaptureButton from "../components/ChartCaptureButton";

const fakeBlob = new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: "image/png" });

vi.mock("html2canvas", () => ({
  default: vi.fn(() => Promise.resolve({
    toBlob: (cb: (b: Blob) => void) => cb(fakeBlob),
  })),
}));

beforeEach(() => {
  localStorage.clear();
  global.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ id: 42 }) }),
  ) as never;
});

describe("ChartCaptureButton", () => {
  it("captures chart, posts PNG, stores image ID in localStorage", async () => {
    const ref = { current: document.createElement("div") };
    render(<ChartCaptureButton targetRef={ref} caption="SPY 5m" />);
    fireEvent.click(screen.getByRole("button", { name: /capture/i }));
    await waitFor(() => {
      const stored = JSON.parse(localStorage.getItem("staged_image_ids") || "[]");
      expect(stored).toEqual([42]);
    });
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/snapshots/images/?staged=true",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
