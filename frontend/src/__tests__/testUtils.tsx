import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { vi } from "vitest";
import { ToastProvider } from "@/hooks/useToast";

export function newQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

type ProviderOptions = {
  client?: QueryClient;
  initialEntries?: string[];
  routePath?: string;
  routes?: Array<{ path: string; element: ReactNode }>;
};

export function renderWithProviders(
  ui: ReactElement,
  { client = newQueryClient(), initialEntries, routePath, routes }: ProviderOptions = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    let content: ReactNode;
    if (routes && routes.length > 0) {
      content = (
        <Routes>
          {routes.map(({ path, element }) => (
            <Route key={path} path={path} element={element} />
          ))}
        </Routes>
      );
    } else if (routePath) {
      content = (
        <Routes>
          <Route path={routePath} element={children} />
        </Routes>
      );
    } else {
      content = children;
    }
    const router = (
      <MemoryRouter initialEntries={initialEntries}>{content}</MemoryRouter>
    );
    return (
      <QueryClientProvider client={client}>
        <ToastProvider>{router}</ToastProvider>
      </QueryClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper });
}

type FetchResponse = { ok: boolean; status?: number; json?: () => Promise<unknown> };

export function mockFetch(responder: (url: string) => FetchResponse | Promise<FetchResponse>): void {
  globalThis.fetch = vi.fn((url: string) => Promise.resolve(responder(url))) as never;
}

// ---- New: hookWrapper for renderHook() ----
export function hookWrapper(client: QueryClient = newQueryClient()) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    );
  };
}

// ---- New: LocationProbe for asserting navigation ----
export function LocationProbe({ onChange }: { onChange: (path: string) => void }) {
  const loc = useLocation();
  onChange(loc.pathname + loc.search);
  return null;
}

// ---- New: mockApi / mockApiError ----
type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export type Route = `${Method} ${string}`;
type ErrorHandler = { status: number; body?: unknown; code?: string; message?: string };
type FnHandler = (body: unknown, url: string) => unknown;
type Handler = unknown | FnHandler | ErrorHandler;

export type FetchCall = { url: string; method: string; body?: unknown };
export type FetchMock = { calls: FetchCall[]; restore: () => void };

function isErrorHandler(h: Handler): h is ErrorHandler {
  if (!h || typeof h !== "object") return false;
  const status = (h as { status?: unknown }).status;
  // ErrorHandler.status is a number (HTTP code). Response payloads with a
  // string `status` field (e.g. Snapshot.status="ready") must not be treated
  // as errors.
  return typeof status === "number";
}

export function mockApi(routes: Record<Route, Handler>): FetchMock {
  const calls: FetchCall[] = [];
  const entries: Array<[string, string, Handler]> = Object.entries(routes).map(([key, h]) => {
    const [method, path] = key.split(" ", 2);
    return [method, path, h];
  });
  // Sort longest path first so more-specific routes win over prefix matches.
  entries.sort((a, b) => b[1].length - a[1].length);

  const fetchImpl = vi.fn(async (url: string, opts?: RequestInit) => {
    const method = (opts?.method ?? "GET").toUpperCase();
    const parsed = url.includes("?") ? url.split("?")[0] : url;
    let body: unknown;
    if (opts?.body !== undefined && typeof opts.body === "string") {
      try {
        body = JSON.parse(opts.body);
      } catch {
        body = opts.body;
      }
    }
    calls.push({ url, method, body });

    const match = entries.find(([m, p]) => m === method && parsed.endsWith(p));
    if (!match) {
      throw new Error(`mockApi: no handler for ${method} ${url}`);
    }
    const [, , handler] = match;
    const resolved = typeof handler === "function" ? (handler as FnHandler)(body, url) : handler;

    if (isErrorHandler(resolved)) {
      return {
        ok: false,
        status: resolved.status,
        statusText: String(resolved.status),
        json: async () => ({
          code: resolved.code ?? "error",
          message: resolved.message ?? "err",
          ...(resolved.body as object ?? {}),
        }),
      };
    }
    if (resolved === undefined) {
      return { ok: true, status: 204, json: async () => ({}) };
    }
    return { ok: true, status: 200, json: async () => resolved };
  });
  vi.stubGlobal("fetch", fetchImpl);
  return { calls, restore: () => { vi.unstubAllGlobals(); } };
}

export function mockApiError(route: string, status: number, code = "error", message = "err"): FetchMock {
  return mockApi({ [route]: { status, code, message } } as Record<Route, Handler>);
}

// ---- New: installFakeWebSocket / FakeSocket ----
type FakeListener = (ev: MessageEvent | Event | CloseEvent) => void;

export class FakeSocket {
  readyState = 0; // CONNECTING
  listeners: Record<string, FakeListener[]> = {};
  sent: unknown[] = [];
  constructor(public url: string) {}
  addEventListener(type: string, listener: FakeListener): void {
    (this.listeners[type] ??= []).push(listener);
  }
  removeEventListener(type: string, listener: FakeListener): void {
    this.listeners[type] = (this.listeners[type] ?? []).filter((l) => l !== listener);
  }
  send(data: string): void {
    try {
      this.sent.push(JSON.parse(data));
    } catch {
      this.sent.push(data);
    }
  }
  close(): void {
    this.readyState = 3; // CLOSED
    (this.listeners.close ?? []).forEach((l) => l(new Event("close") as CloseEvent));
  }
  emitOpen(): void {
    if (this.readyState === 3) return;
    this.readyState = 1;
    (this.listeners.open ?? []).forEach((l) => l(new Event("open")));
  }
  emitMessage(data: unknown): void {
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    (this.listeners.message ?? []).forEach((l) =>
      l(new MessageEvent("message", { data: payload })),
    );
  }
  emitClose(code = 1000): void {
    this.readyState = 3;
    (this.listeners.close ?? []).forEach((l) => l(new CloseEvent("close", { code })));
  }
}

export type FakeWebSocketController = {
  sockets: FakeSocket[];
  find(urlSuffix: string): FakeSocket | undefined;
  restore(): void;
};

export function installFakeWebSocket(): FakeWebSocketController {
  const sockets: FakeSocket[] = [];
  class Stub extends FakeSocket {
    constructor(url: string) {
      super(url);
      sockets.push(this);
    }
  }
  vi.stubGlobal("WebSocket", Stub);
  return {
    sockets,
    find: (suffix) => sockets.find((s) => s.url.endsWith(suffix)),
    restore: () => { vi.unstubAllGlobals(); },
  };
}
