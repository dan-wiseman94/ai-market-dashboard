import { vi, test, expect, afterEach } from "vitest";
import { fetchCostsSummary, fetchCostsCaps, fetchCostsSnapshot } from "@/api/costs";

// Restore the fetch spy between tests so each test's mock.calls starts empty
// (vitest 4 reuses the existing spy across tests rather than re-creating it).
afterEach(() => {
  vi.restoreAllMocks();
});

test("fetchCostsSummary GETs /api/costs/summary with range", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
    new Response(JSON.stringify({ total: "0", by_provider: [], by_model: [], by_thread: [], daily: [] })),
  );
  await fetchCostsSummary({ from: "2026-04-01T00:00:00Z", to: "2026-04-18T00:00:00Z" });
  const url = fetchSpy.mock.calls[0][0] as string;
  expect(url).toContain("/api/costs/summary");
  expect(url).toContain("from=2026-04-01");
  expect(url).toContain("to=2026-04-18");
});

test("fetchCostsCaps returns list", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("[]"));
  const out = await fetchCostsCaps();
  expect(Array.isArray(out)).toBe(true);
});

test("fetchCostsSnapshot GETs /api/costs/snapshot/:id", async () => {
  const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("[]"));
  await fetchCostsSnapshot(42);
  expect(fetchSpy.mock.calls[0][0]).toContain("/api/costs/snapshot/42");
});
