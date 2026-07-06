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

  it("parses the hand-rolled {code, message} envelope", async () => {
    stubFetchOnce({
      ok: false,
      status: 409,
      statusText: "Conflict",
      json: async () => ({ code: "conflict", message: "Cannot delete: still referenced." }),
    });
    await expect(apiGet("/api/y/")).rejects.toMatchObject({
      status: 409,
      code: "conflict",
      message: "Cannot delete: still referenced.",
    });
  });

  it("falls back to the DRF {detail} envelope", async () => {
    stubFetchOnce({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: async () => ({ detail: "Not found." }),
    });
    await expect(apiGet("/api/y/")).rejects.toMatchObject({ status: 404, message: "Not found." });
  });

  it("flattens a DRF field-keyed validation dict into a readable message", async () => {
    stubFetchOnce({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: async () => ({
        rationale: ["This field may not be blank."],
        non_field_errors: ["Provide an invalidation price or note."],
      }),
    });
    await expect(apiGet("/api/y/")).rejects.toMatchObject({
      status: 400,
      message: "rationale: This field may not be blank.; Provide an invalidation price or note.",
    });
  });

  it("degrades to statusText when the error body is not a recognized shape", async () => {
    stubFetchOnce({
      ok: false,
      status: 500,
      statusText: "Server Error",
      json: async () => ({ unexpected: 123 }),
    });
    await expect(apiGet("/api/y/")).rejects.toMatchObject({
      status: 500,
      message: "Server Error",
    });
  });

  it("resolves void on 204 No Content", async () => {
    stubFetchOnce({ ok: true, status: 204 });
    await expect(apiDelete("/api/y/")).resolves.toBeUndefined();
  });

  it("apiGet resolves null (not undefined) on 204 so react-query accepts it", async () => {
    // A "latest"-style GET that 204s on no-data (e.g. /api/aieval/runs/latest/)
    // must not hand react-query `undefined` — it throws "Query data cannot be
    // undefined". apiGet coalesces the empty 204 body to null.
    stubFetchOnce({ ok: true, status: 204 });
    await expect(apiGet("/api/y/")).resolves.toBeNull();
  });

  it("serializes the request body as JSON on POST", async () => {
    const fetchMock = stubFetchOnce({ ok: true, status: 201, json: async () => ({ id: 1 }) });
    await apiPost("/api/x/", { name: "A" });
    const [, opts] = fetchMock.mock.calls[0];
    expect(opts.method).toBe("POST");
    expect(opts.body).toBe(JSON.stringify({ name: "A" }));
  });
});
