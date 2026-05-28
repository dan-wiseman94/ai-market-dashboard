import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listNotifications, markNotificationRead, markAllNotificationsRead,
  NotificationDTO,
} from "@/api/observer";
import { formatRelative } from "@/utils/format";

function unwrapResults(data: unknown): NotificationDTO[] {
  if (Array.isArray(data)) return data as NotificationDTO[];
  if (data && typeof data === "object" && "results" in data) {
    return (data as { results: NotificationDTO[] }).results;
  }
  return [];
}

function notificationWsUrl(): string {
  const configured = import.meta.env.VITE_WS_BASE_URL as string | undefined;
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  const base = configured && configured.length > 0 ? configured : `${proto}://${window.location.host}`;
  return `${base}/ws/notifications/`;
}

function desktopNotificationsGranted(): boolean {
  return typeof Notification !== "undefined" && Notification.permission === "granted";
}

function showDesktopNotification(payload: { kind?: string; title: string; body?: string }): void {
  if (payload.kind !== "observer_done" && payload.kind !== "trigger") return;
  try {
    new Notification(payload.title, { body: payload.body });
  } catch {
    /* OS notification unavailable — ignore */
  }
}

function BellIcon({ unread }: { unread: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      className={`h-[18px] w-[18px] transition-colors duration-200 ${
        unread ? "text-copper-300" : "text-ink-300 group-hover:text-ink-100"
      }`}
      fill="none" stroke="currentColor" strokeWidth="1.25"
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden
    >
      <path d="M10 3.5c-2.5 0-4.5 2-4.5 4.5v2.2c0 .5-.2 1-.5 1.4L4 13h12l-1-1.4c-.3-.4-.5-.9-.5-1.4V8c0-2.5-2-4.5-4.5-4.5Z" />
      <path d="M8.5 15a1.5 1.5 0 0 0 3 0" />
    </svg>
  );
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

  useEffect(() => {
    if (typeof WebSocket === "undefined") return;
    const ws = new WebSocket(notificationWsUrl());
    ws.onmessage = (ev: MessageEvent) => {
      try {
        const m = JSON.parse(ev.data);
        if (m.type !== "notification.event") return;
        qc.invalidateQueries({ queryKey: ["notifications"] });
        if (desktopNotificationsGranted()) showDesktopNotification(m.payload);
      } catch {
        /* ignore parse errors */
      }
    };
    return () => ws.close();
  }, [qc]);

  return (
    <div className="relative" data-testid="notification-bell">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="notifications"
        className="group relative p-2 rounded-ledger hover:bg-ink-800/60 transition-colors duration-150 ease-ledger"
      >
        <BellIcon unread={unread > 0} />
        {unread > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 min-w-[16px] h-[16px] px-1 rounded-full bg-copper-500 text-ink-void text-[9px] font-mono font-semibold flex items-center justify-center shadow-copper-glow"
            aria-label={`${unread} unread`}
          >
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute right-0 mt-3 w-96 max-h-[28rem] overflow-hidden rounded-ledger border border-rule-strong shadow-ledger z-50"
          style={{
            background: "linear-gradient(180deg, var(--ink-850) 0%, var(--ink-900) 100%)",
            boxShadow:
              "0 1px 0 rgba(200,150,88,0.18) inset, 0 24px 60px -20px rgba(0,0,0,0.7), 0 0 0 1px rgba(200,150,88,0.06)",
          }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-rule">
            <div className="flex items-center gap-2">
              <span className="ledger-eyebrow">Notifications</span>
              {unread > 0 && (
                <span className="text-[10px] font-mono text-copper-400">
                  {unread} unread
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => markAll.mutate()}
              className="text-[11px] font-mono text-ink-400 hover:text-copper-300 transition-colors"
            >
              Mark all read
            </button>
          </div>

          {typeof Notification !== "undefined" && Notification.permission === "default" && (
            <div className="px-4 py-3 border-b border-rule bg-copper-800/10">
              <div className="text-[12px] text-ink-200">
                Get a desktop notification when the AI fires?
              </div>
              <div className="flex gap-2 mt-2">
                <button
                  type="button"
                  onClick={() => Notification.requestPermission().then(() => setOpen(true))}
                  className="ledger-cta text-[11px] py-1 px-2.5"
                >
                  Enable
                </button>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="ledger-ghost text-[11px] py-1 px-2.5"
                >
                  Not now
                </button>
              </div>
            </div>
          )}

          <ul className="max-h-[22rem] overflow-y-auto">
            {items.length === 0 && (
              <li className="px-4 py-6 text-sm text-ink-500 text-center">
                <div className="font-display italic text-ink-400">Nothing to report.</div>
                <div className="text-[11px] font-mono mt-1 text-ink-500">The tape is quiet.</div>
              </li>
            )}
            {items.map((n) => (
              <li
                key={n.id}
                className={[
                  "relative border-b border-rule-soft transition-colors hover:bg-ink-800/40",
                  n.read_at ? "opacity-60" : "",
                ].join(" ")}
              >
                {!n.read_at && (
                  <span
                    aria-hidden
                    className="absolute left-0 top-0 bottom-0 w-[2px] bg-copper-500"
                  />
                )}
                <Link
                  to={n.link || "#"}
                  onClick={() => { markOne.mutate(n.id); setOpen(false); }}
                  className="block px-4 py-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-[13px] font-medium text-ink-100">{n.title}</div>
                    <div className="text-[10px] font-mono text-ink-500 shrink-0 pt-0.5">
                      {formatRelative(n.created_at)}
                    </div>
                  </div>
                  {n.body && (
                    <div className="text-[12px] text-ink-300 mt-0.5 line-clamp-2">
                      {n.body}
                    </div>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
