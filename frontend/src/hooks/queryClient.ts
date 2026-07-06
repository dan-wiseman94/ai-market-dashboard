import { QueryCache, QueryClient } from "@tanstack/react-query";
import { emitToast } from "./toastBridge";

export const queryClient = new QueryClient({
  // One policy for every query: a failed fetch surfaces as an error toast rather
  // than an eternal skeleton or a false "empty" state. Pages still branch on
  // isError for their own inline treatment; this guarantees the user is told.
  queryCache: new QueryCache({
    onError: (error) => {
      const message = error instanceof Error && error.message ? error.message : "Request failed";
      emitToast({ kind: "error", text: message });
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 1000,
      gcTime: 60_000,
      retry: (failureCount, err: unknown) => {
        const e = err as { status?: number } | undefined;
        if (e?.status && e.status >= 400 && e.status < 500) return false;
        return failureCount < 2;
      },
      refetchOnWindowFocus: true,
    },
  },
});
