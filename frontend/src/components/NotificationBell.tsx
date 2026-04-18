import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listNotifications, markNotificationRead, markAllNotificationsRead,
  NotificationDTO,
} from "@/api/observer";

function unwrapResults(data: unknown): NotificationDTO[] {
  if (Array.isArray(data)) return data as NotificationDTO[];
  if (data && typeof data === "object" && "results" in data) {
    return (data as { results: NotificationDTO[] }).results;
  }
  return [];
}

export default function NotificationBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: () => listNotifications(false),
  });
  const items = useMemo(() => unwrapResults(data), [data]);
  const unread = items.filter((n) => n.read_at === null).length;

  const markOne = useMutation({
    mutationFn: (id: number) => markNotificationRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
  const markAll = useMutation({
    mutationFn: () => markAllNotificationsRead(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  // Live updates via WebSocket
  useEffect(() => {
    if (typeof WebSocket === "undefined") return;
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/notifications/`);
    ws.onmessage = (ev: MessageEvent) => {
      try {
        const m = JSON.parse(ev.data);
        if (m.type === "notification.event") {
          qc.invalidateQueries({ queryKey: ["notifications"] });
          if (typeof Notification !== "undefined" && Notification.permission === "granted") {
            const p = m.payload;
            if (p.kind === "observer_done" || p.kind === "trigger") {
              try { new Notification(p.title, { body: p.body }); } catch { /* no-op */ }
            }
          }
        }
      } catch { /* ignore parse errors */ }
    };
    return () => ws.close();
  }, [qc]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="notifications"
        className="relative p-2 rounded hover:bg-slate-800"
      >
        🔔
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 text-xs bg-red-600 text-white rounded-full px-1 min-w-[18px] text-center">
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto bg-slate-900 border border-slate-700 rounded shadow-xl z-50">
          <div className="p-2 border-b border-slate-700 flex justify-between text-xs text-slate-400">
            <span>Notifications</span>
            <button type="button" onClick={() => markAll.mutate()}
                    className="hover:text-white">Mark all read</button>
          </div>

          {typeof Notification !== "undefined" && Notification.permission === "default" && (
            <div className="p-3 border-b border-slate-800 text-xs">
              Get a desktop notification when the AI fires?
              <div className="flex gap-2 mt-2">
                <button type="button"
                        onClick={() => Notification.requestPermission().then(() => setOpen(true))}
                        className="px-2 py-1 rounded bg-emerald-600 hover:bg-emerald-500">Enable</button>
                <button type="button" onClick={() => setOpen(false)}
                        className="px-2 py-1 rounded bg-slate-700 hover:bg-slate-600">Not now</button>
              </div>
            </div>
          )}

          <ul>
            {items.length === 0 && (
              <li className="p-3 text-sm text-slate-500">No notifications.</li>
            )}
            {items.map((n) => (
              <li key={n.id} className={`p-3 border-b border-slate-800 ${n.read_at ? "opacity-50" : ""}`}>
                <Link
                  to={n.link || "#"}
                  onClick={() => { markOne.mutate(n.id); setOpen(false); }}
                  className="block"
                >
                  <div className="text-sm font-semibold">{n.title}</div>
                  {n.body && <div className="text-xs text-slate-400">{n.body}</div>}
                  <div className="text-xs text-slate-500 mt-1">
                    {new Date(n.created_at).toLocaleString()}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
