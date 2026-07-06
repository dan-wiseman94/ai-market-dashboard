import { afterEach, describe, expect, it, vi } from "vitest";
import { emitToast, registerToastHandler } from "@/hooks/toastBridge";
import { queryClient } from "@/hooks/queryClient";

afterEach(() => {
  registerToastHandler(null);
  queryClient.clear();
});

describe("toastBridge", () => {
  it("routes emits to the registered handler and stops after unregister", () => {
    const handler = vi.fn();
    registerToastHandler(handler);
    emitToast({ kind: "error", text: "boom" });
    expect(handler).toHaveBeenCalledWith({ kind: "error", text: "boom" });

    registerToastHandler(null);
    emitToast({ kind: "info", text: "ignored" });
    expect(handler).toHaveBeenCalledTimes(1);
  });
});

describe("queryClient error policy", () => {
  it("emits an error toast with the error message when a query fails", async () => {
    const handler = vi.fn();
    registerToastHandler(handler);

    await expect(
      queryClient.fetchQuery({
        queryKey: ["policy-test-failure"],
        queryFn: () => Promise.reject(new Error("Not found.")),
        retry: false,
      }),
    ).rejects.toThrow("Not found.");

    expect(handler).toHaveBeenCalledWith({ kind: "error", text: "Not found." });
  });

  it("falls back to a generic message when the error has no message", async () => {
    const handler = vi.fn();
    registerToastHandler(handler);

    await expect(
      queryClient.fetchQuery({
        queryKey: ["policy-test-empty"],
        queryFn: () => Promise.reject(new Error("")),
        retry: false,
      }),
    ).rejects.toBeInstanceOf(Error);

    expect(handler).toHaveBeenCalledWith({ kind: "error", text: "Request failed" });
  });
});
