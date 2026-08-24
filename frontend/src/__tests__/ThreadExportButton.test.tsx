import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { test, expect } from "vitest";
import { mockApi, renderWithProviders } from "./testUtils";
import ThreadExportButton from "@/components/ThreadExportButton";

test("clicking button POSTs to per-thread export endpoint", async () => {
  const api = mockApi({ "POST /api/export/thread/42/": { id: 7, status: "pending" } });
  renderWithProviders(<ThreadExportButton threadId={42} />);
  await userEvent.click(screen.getByRole("button", { name: /export/i }));
  const called = api.calls.some(
    (c) => c.url.includes("/api/export/thread/42/") && c.method === "POST",
  );
  expect(called).toBe(true);
});
