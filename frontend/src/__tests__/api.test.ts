import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiDelete, apiGet, apiPost } from "../api/client";

function stubFetchOnce(response: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed JSON on 200", async () => {
    stubFetchOnce({ ok: true, status: 200, json: async () => ({ hello: "world" }) });
    const result = await apiGet<{ hello: string }>("/api/x/");
    expect(result).toEqual({ hello: "world" });
  });

  it("throws ApiError on non-2xx responses", async () => {
    stubFetchOnce({
      ok: false,
      status: 503,
      statusText: "bad",
      json: async () => ({ code: "oops", message: "nope" }),
    });
    await expect(apiGet("/api/y/")).rejects.toBeInstanceOf(ApiError);
  });

  it("resolves void on 204 No Content", async () => {
    stubFetchOnce({ ok: true, status: 204 });
    await expect(apiDelete("/api/y/")).resolves.toBeUndefined();
  });

  it("serializes the request body as JSON on POST", async () => {
    const fetchMock = stubFetchOnce({ ok: true, status: 201, json: async () => ({ id: 1 }) });
    await apiPost("/api/x/", { name: "A" });
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ name: "A" }));
  });
});
