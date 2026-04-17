import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiGet, apiPost, apiDelete } from "../api/client";

type MockFetch = { mockResolvedValue: (v: unknown) => void };

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("apiGet returns JSON on 200", async () => {
    (globalThis.fetch as unknown as MockFetch).mockResolvedValue({
      ok: true, status: 200, json: async () => ({ hello: "world" }),
    });
    const v = await apiGet<{ hello: string }>("/api/x/");
    expect(v).toEqual({ hello: "world" });
  });

  it("throws ApiError on non-2xx", async () => {
    (globalThis.fetch as unknown as MockFetch).mockResolvedValue({
      ok: false, status: 503, statusText: "bad", json: async () => ({ code: "oops", message: "nope" }),
    });
    await expect(apiGet("/api/y/")).rejects.toBeInstanceOf(ApiError);
  });

  it("apiDelete resolves void on 204", async () => {
    (globalThis.fetch as unknown as MockFetch).mockResolvedValue({ ok: true, status: 204 });
    await expect(apiDelete("/api/y/")).resolves.toBeUndefined();
  });

  it("apiPost sends JSON body", async () => {
    const mock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: 1 }) });
    vi.stubGlobal("fetch", mock);
    await apiPost("/api/x/", { name: "A" });
    const [, opts] = mock.mock.calls[0];
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ name: "A" }));
  });
});
