import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FileAttach from "@/pages/thread-detail/FileAttach";
import { mockApi, renderWithProviders } from "./testUtils";

const FILE = {
  id: 3,
  anthropic_id: "file_abc",
  kind: "filing",
  ticker: "AAPL",
  mime: "application/pdf",
  size: 2048,
  filename: "10k.pdf",
};

function thread(provider: string | null) {
  return {
    id: 5,
    kind: "consult",
    title: "T",
    profile:
      provider === null
        ? null
        : { id: 1, name: "P", default_provider: provider, default_model: "m" },
    pinned_snapshot_id: null,
    created_at: "2026-01-01T00:00:00Z",
    messages: [],
  };
}

function setup(provider: string | null, extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/files/": { results: [FILE] },
    "GET /api/threads/5/": thread(provider),
    ...extra,
  } as Parameters<typeof mockApi>[0]);
}

afterEach(() => vi.unstubAllGlobals());

describe("FileAttach — Claude-only capability", () => {
  it("offers attach normally for a Claude profile", async () => {
    setup("claude");
    renderWithProviders(<FileAttach threadId={5} />);
    const attach = await screen.findByRole("button", { name: "Attach 10k.pdf" });
    expect(attach).toBeEnabled();
    expect(screen.queryByTestId("files-claude-only")).toBeNull();
  });

  it("explains the gap and disables attach for a non-Claude profile", async () => {
    setup("openai");
    renderWithProviders(<FileAttach threadId={5} />);
    const note = await screen.findByTestId("files-claude-only");
    expect(note).toHaveTextContent(/OpenAI/);
    expect(note).toHaveTextContent(/Claude-only/);
    expect(await screen.findByRole("button", { name: "Attach 10k.pdf" })).toBeDisabled();
  });

  it("stays permissive when the thread has no profile at all", async () => {
    setup(null);
    renderWithProviders(<FileAttach threadId={5} />);
    expect(await screen.findByRole("button", { name: "Attach 10k.pdf" })).toBeEnabled();
  });
});

describe("FileAttach — delete", () => {
  it("names the upstream provider deletion in the confirmation and DELETEs on confirm", async () => {
    // Typed param so the assertion below can read the prompt text.
    const confirmSpy = vi.fn((message?: string) => message !== undefined);
    vi.stubGlobal("confirm", confirmSpy);
    const { calls } = setup("claude", { "DELETE /api/files/3/": undefined });

    renderWithProviders(<FileAttach threadId={5} />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete 10k.pdf" }));

    const prompt = String(confirmSpy.mock.calls[0][0]);
    expect(prompt).toContain("10k.pdf");
    expect(prompt).toMatch(/upstream at the provider/i);
    expect(prompt).toMatch(/cannot be undone/i);

    await waitFor(() =>
      expect(calls.some((c) => c.method === "DELETE" && c.url === "/api/files/3/")).toBe(true),
    );
  });

  it("sends nothing when the confirmation is declined", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    const { calls } = setup("claude", { "DELETE /api/files/3/": undefined });

    renderWithProviders(<FileAttach threadId={5} />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete 10k.pdf" }));

    expect(calls.some((c) => c.method === "DELETE")).toBe(false);
  });
});

describe("FileAttach — attach", () => {
  it("POSTs the file id with a default prompt", async () => {
    const { calls } = setup("claude", {
      "POST /api/threads/5/attach-file/": { message_id: 11 },
    });
    renderWithProviders(<FileAttach threadId={5} />);
    fireEvent.click(await screen.findByRole("button", { name: "Attach 10k.pdf" }));

    await waitFor(() => {
      const post = calls.find((c) => c.url === "/api/threads/5/attach-file/");
      expect(post?.body).toEqual({ file_id: 3, prompt: "Please review this document." });
    });
  });
});
