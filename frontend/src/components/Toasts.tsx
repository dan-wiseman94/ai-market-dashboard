import { useToast, type ToastKind } from "../hooks/useToast";

const TONE: Record<ToastKind, string> = {
  info: "bg-slate-800 text-slate-100 border-slate-600",
  success: "bg-emerald-500/10 text-emerald-800 border-emerald-500/40 dark:bg-emerald-900 dark:text-emerald-100 dark:border-emerald-700",
  error: "bg-rose-500/10 text-rose-800 border-rose-500/40 dark:bg-rose-900 dark:text-rose-100 dark:border-rose-700",
};

export function Toasts() {
  const { toasts, dismiss } = useToast();
  return (
    <div
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2"
      role="region"
      aria-label="Notifications"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`px-4 py-2 border rounded shadow-lg cursor-pointer ${TONE[t.kind]}`}
          data-testid={`toast-${t.kind}`}
          onClick={() => dismiss(t.id)}
        >
          {t.text}
        </div>
      ))}
    </div>
  );
}
