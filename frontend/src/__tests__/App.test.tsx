import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows 'Checking…' before the health check resolves", () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {
        /* never resolve */
      }),
    );
    render(<App />);
    expect(screen.getByText(/checking/i)).toBeInTheDocument();
  });

  it("renders 'Stack is green' when /api/health returns status ok", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    } as Response);

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/stack is green/i)).toBeInTheDocument();
    });
  });

  it("renders 'Stack is down' when /api/health fails", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("boom"));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/stack is down/i)).toBeInTheDocument();
    });
  });
});
