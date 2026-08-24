import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  useAttachFileToThread,
  useFiles,
  useUploadFile,
  type UserFile,
} from "@/hooks/useFiles";
import { ApiError } from "@/api/client";
import { hookWrapper, mockApi, mockApiError, newQueryClient } from "../testUtils";

const FILE: UserFile = {
  id: 1,
  anthropic_id: "file_abc",
  kind: "filing",
  ticker: "AAPL",
  mime: "application/pdf",
  size: 1024,
  filename: "10k.pdf",
};

describe("useFiles (query)", () => {
  it("fetches the unfiltered list and unwraps results", async () => {
    const { calls } = mockApi({ "GET /api/files/": { results: [FILE] } });
    const { result } = renderHook(() => useFiles(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([FILE]);
    // No kind => no query string.
    expect(calls[0].url).toBe("/api/files/");
  });

  it("appends an encoded kind filter to the URL", async () => {
    const { calls } = mockApi({ "GET /api/files/": { results: [] } });
    const { result } = renderHook(() => useFiles("earnings call"), {
      wrapper: hookWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(calls[0].url).toBe("/api/files/?kind=earnings%20call");
  });

  it("returns [] when the payload has no results key", async () => {
    mockApi({ "GET /api/files/": {} });
    const { result } = renderHook(() => useFiles(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });

  it("surfaces the server error envelope as an ApiError", async () => {
    mockApiError("GET /api/files/", 500, "error", "boom");
    const { result } = renderHook(() => useFiles(), { wrapper: hookWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(500);
    expect(err.message).toBe("boom");
  });
});

describe("useUploadFile", () => {
  it("POSTs the FormData and invalidates the files query", async () => {
    const qc = newQueryClient();
    // Seed a stale files query so we can prove it gets invalidated.
    qc.setQueryData(["files", ""], [FILE]);
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");
    const { calls } = mockApi({ "POST /api/files/": FILE });

    const { result } = renderHook(() => useUploadFile(), {
      wrapper: hookWrapper(qc),
    });
    const form = new FormData();
    form.append("kind", "filing");
    let data: unknown;
    await act(async () => {
      data = await result.current.mutateAsync(form);
    });

    expect(data).toEqual(FILE);
    expect(calls[0].method).toBe("POST");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["files"] });
  });

  it("rejects when the upload fails", async () => {
    mockApiError("POST /api/files/", 400);
    const { result } = renderHook(() => useUploadFile(), {
      wrapper: hookWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync(new FormData()).catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useAttachFileToThread", () => {
  it("POSTs file_id + prompt as JSON to the thread's attach-file route", async () => {
    const { calls } = mockApi({
      "POST /api/threads/7/attach-file/": { message_id: 5 },
    });
    const { result } = renderHook(() => useAttachFileToThread(7), {
      wrapper: hookWrapper(),
    });
    await act(async () => {
      await result.current.mutateAsync({ fileId: 42, prompt: "summarize" });
    });
    expect(calls[0].url).toBe("/api/threads/7/attach-file/");
    expect(calls[0].body).toEqual({ file_id: 42, prompt: "summarize" });
  });

  it("rejects with the server's validation message, not a fixed string", async () => {
    mockApiError("POST /api/threads/7/attach-file/", 404, "not_found", "File not found");
    const { result } = renderHook(() => useAttachFileToThread(7), {
      wrapper: hookWrapper(),
    });
    await act(async () => {
      await result.current
        .mutateAsync({ fileId: 1, prompt: "x" })
        .catch(() => {});
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(404);
    expect(err.code).toBe("not_found");
    expect(err.message).toBe("File not found");
  });
});
