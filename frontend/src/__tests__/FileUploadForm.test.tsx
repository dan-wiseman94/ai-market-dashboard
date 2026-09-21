import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/api/client";
import { FileUploadForm, uploadErrorText } from "@/components/FileUploadForm";
import { mockApi, renderWithProviders } from "./testUtils";

const CREATED = {
  id: 9,
  anthropic_id: "file_abc",
  kind: "research",
  ticker: "AAPL",
  mime: "application/pdf",
  size: 1024,
  filename: "note.pdf",
};

function pick(name = "note.pdf", type = "application/pdf"): File {
  const file = new File(["x"], name, { type });
  const input = screen.getByLabelText("File");
  fireEvent.change(input, { target: { files: [file] } });
  return file;
}

afterEach(() => vi.unstubAllGlobals());

describe("uploadErrorText", () => {
  it("reports the 413 size rejection specifically, quoting the server's limit", () => {
    const err = new ApiError(413, "file_too_large", "File is 40000000 bytes; the limit is 33554432.");
    const text = uploadErrorText(err);
    expect(text).toMatch(/over the upload limit/i);
    expect(text).toContain("the limit is 33554432");
    // Must NOT degrade to the generic failure line.
    expect(text).not.toBe("Upload failed.");
  });

  it("points a missing-key failure at the settings page", () => {
    expect(uploadErrorText(new ApiError(400, "no_key", "Claude key not configured"))).toMatch(
      /Claude API key/,
    );
  });

  it("falls back to the server message for any other ApiError", () => {
    expect(uploadErrorText(new ApiError(500, "error", "boom"))).toBe("boom");
  });

  it("falls back to a generic line for a non-ApiError throw", () => {
    expect(uploadErrorText(new TypeError("network"))).toBe("Upload failed.");
  });
});

describe("FileUploadForm", () => {
  it("groups the controls in a labelled fieldset with described help text", () => {
    renderWithProviders(<FileUploadForm />);
    expect(screen.getByRole("group", { name: "Upload a document" })).toBeInTheDocument();
    const file = screen.getByLabelText("File");
    const describedBy = file.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)?.textContent).toMatch(/32 MB/);
    expect(screen.getByLabelText("Kind")).toBeInTheDocument();
    expect(screen.getByLabelText("Symbol")).toBeInTheDocument();
  });

  it("refuses to POST when no file is chosen", () => {
    const { calls } = mockApi({ "POST /api/files/": CREATED });
    renderWithProviders(<FileUploadForm />);
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a file to upload.");
    expect(calls).toHaveLength(0);
  });

  it("POSTs multipart with the chosen kind and an upper-cased ticker", async () => {
    const onUploaded = vi.fn();
    const bodies: FormData[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string, opts?: RequestInit) => {
        bodies.push(opts?.body as FormData);
        return { ok: true, status: 201, json: async () => CREATED };
      }),
    );
    renderWithProviders(<FileUploadForm onUploaded={onUploaded} />);
    pick();
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "filing" } });
    fireEvent.change(screen.getByLabelText("Symbol"), { target: { value: "aapl" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith(CREATED));
    const sent = bodies[0];
    expect(sent.get("kind")).toBe("filing");
    expect(sent.get("ticker")).toBe("AAPL");
    expect((sent.get("file") as File).name).toBe("note.pdf");
    expect(screen.getByRole("status")).toHaveTextContent("Uploaded note.pdf.");
  });

  it("surfaces the 413 cap as its own message, not a generic failure", async () => {
    mockApi({
      "POST /api/files/": {
        status: 413,
        code: "file_too_large",
        message: "File is 40000000 bytes; the limit is 33554432.",
      },
    });
    renderWithProviders(<FileUploadForm />);
    pick("huge.pdf");
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/over the upload limit/i);
    expect(alert).toHaveTextContent("the limit is 33554432");
    // The success line must not appear alongside the failure.
    expect(screen.queryByRole("status")).toBeNull();
  });
});
