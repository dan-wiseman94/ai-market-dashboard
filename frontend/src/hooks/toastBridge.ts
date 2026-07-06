import type { Toast } from "./useToast";

/**
 * Out-of-tree toast bridge.
 *
 * The `queryClient` is constructed at module scope (hooks/queryClient.ts),
 * outside the React tree where `<ToastProvider>` lives, so its QueryCache
 * `onError` policy cannot call the `useToast` hook. The mounted provider
 * registers its `push` here; module-level code (the query error policy) emits
 * through `emitToast`. If no provider is mounted, emits are dropped silently.
 */
type PushFn = (t: Omit<Toast, "id">) => void;

let handler: PushFn | null = null;

export function registerToastHandler(fn: PushFn | null): void {
  handler = fn;
}

export function emitToast(t: Omit<Toast, "id">): void {
  handler?.(t);
}
