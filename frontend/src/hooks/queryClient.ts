import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
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
