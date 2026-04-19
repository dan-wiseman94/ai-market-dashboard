import { useToast, type ToastKind } from "../hooks/useToast";

const TONE: Record<ToastKind, string> = {
  info: "bg-slate-800 text-slate-100 border-slate-600",
  success: "bg-emerald-900 text-emerald-100 border-emerald-700",
  error: "bg-rose-900 text-rose-100 border-rose-700",
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
