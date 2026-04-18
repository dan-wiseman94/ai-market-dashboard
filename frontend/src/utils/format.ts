/** Formatting helpers for numbers, money, P/L tone, and timestamps. */

export function fmt(n: number | null | undefined, digits = 2): string {
  if (n == null) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function signed(n: number, digits = 2): string {
  return `${n > 0 ? "+" : ""}${fmt(n, digits)}`;
}

export function usd(n: number | string | null | undefined, digits = 4): string {
  if (n == null || n === "") return "—";
  const v = typeof n === "string" ? Number(n) : n;
  if (!Number.isFinite(v)) return "—";
  return `$${v.toFixed(digits)}`;
}

export function plClass(n: number): string {
  if (n > 0) return "text-gain";
  if (n < 0) return "text-loss";
  return "text-ink-400";
}

/** "just now" / "3m ago" / "2h ago" / "Apr 12" — same semantics as prior NotificationBell helper. */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const d = new Date(iso);
  const min = Math.floor((now - d.getTime()) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
