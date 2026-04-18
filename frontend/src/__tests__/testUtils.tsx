import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";

export function newQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

type ProviderOptions = {
  client?: QueryClient;
  initialEntries?: string[];
  routePath?: string;
};

export function renderWithProviders(
  ui: ReactElement,
  { client = newQueryClient(), initialEntries, routePath }: ProviderOptions = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    const router = (
      <MemoryRouter initialEntries={initialEntries}>
        {routePath ? (
          <Routes>
            <Route path={routePath} element={children} />
          </Routes>
        ) : (
          children
        )}
      </MemoryRouter>
    );
    return <QueryClientProvider client={client}>{router}</QueryClientProvider>;
  }
  return render(ui, { wrapper: Wrapper });
}

type FetchResponse = { ok: boolean; status?: number; json?: () => Promise<unknown> };

export function mockFetch(responder: (url: string) => FetchResponse | Promise<FetchResponse>): void {
  globalThis.fetch = vi.fn((url: string) => Promise.resolve(responder(url))) as never;
}
