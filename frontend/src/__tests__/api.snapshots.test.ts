import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchSnapshotDiff } from "../api/snapshots";

function stubOk(body: unknown): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("api/snapshots.fetchSnapshotDiff", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("hits the diff endpoint without query when no against is passed", async () => {
    const fetchMock = stubOk({ delta: "", prev_id: 0, curr_id: 5 });
    await fetchSnapshotDiff(5);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/snapshots/5/diff/");
  });

  it("includes the against query param when provided", async () => {
    const fetchMock = stubOk({ delta: "x", prev_id: 3, curr_id: 5 });
    await fetchSnapshotDiff(5, 3);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/snapshots/5/diff/?against=3");
  });
});
