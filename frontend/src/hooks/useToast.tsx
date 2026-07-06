/* eslint-disable react-refresh/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { registerToastHandler } from "./toastBridge";

export type ToastKind = "info" | "success" | "error";
export interface Toast {
  id: number;
  kind: ToastKind;
  text: string;
}

interface ToastContextValue {
  toasts: Toast[];
  push: (t: Omit<Toast, "id">) => void;
  dismiss: (id: number) => void;
}

const Ctx = createContext<ToastContextValue | null>(null);

export function ToastProvider({
  children,
  defaultDurationMs = 4000,
}: {
  children: ReactNode;
  defaultDurationMs?: number;
}) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  // Track pending auto-dismiss timers so they can be cleared on unmount — otherwise a
  // toast pushed shortly before unmount fires its dismiss() (a setState) after the tree
  // is gone, leaking across React-Testing-Library teardown (a stray "window is not
  // defined" once the jsdom env is torn down) and wasting work in production.
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
    setToasts((xs) => xs.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (t: Omit<Toast, "id">) => {
      const id = nextId.current++;
      setToasts((xs) => [...xs, { ...t, id }]);
      timers.current.set(id, setTimeout(() => dismiss(id), defaultDurationMs));
    },
    [defaultDurationMs, dismiss],
  );

  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
    };
  }, []);

  // Expose this provider's push to out-of-tree emitters (the queryClient error
  // policy) while it is mounted; unregister on unmount so a torn-down provider
  // never receives an emit.
  useEffect(() => {
    registerToastHandler(push);
    return () => registerToastHandler(null);
  }, [push]);

  const value = useMemo(
    () => ({ toasts, push, dismiss }),
    [toasts, push, dismiss],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useToast(): ToastContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useToast must be used inside <ToastProvider>");
  return v;
}
