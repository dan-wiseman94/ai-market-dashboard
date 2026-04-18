import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { sendMessage } from "../api/threads";

function stubOk(body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("api/threads.sendMessage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts plain text body when no override provided", async () => {
    const fetchMock = stubOk({ id: 1 });
    await sendMessage(42, "hi");
    const [url, opts] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/threads/42/send/");
    expect(JSON.parse(opts.body)).toEqual({
      text: "hi",
      override_provider: undefined,
      override_model: undefined,
    });
  });

  it("forwards provider+model override when supplied", async () => {
    const fetchMock = stubOk({ id: 2 });
    await sendMessage(7, "hello", { provider: "openai", model: "gpt-5-mini" });
    const [, opts] = fetchMock.mock.calls[0];
    expect(JSON.parse(opts.body)).toEqual({
      text: "hello",
      override_provider: "openai",
      override_model: "gpt-5-mini",
    });
  });
});
