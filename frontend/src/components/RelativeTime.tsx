import { formatDistanceToNow } from "date-fns";

/**
 * A relative timestamp ("3 minutes ago"). Uses a semantic <time> element (the
 * absolute value is in `dateTime` for assistive tech) and a stable
 * `data-testid="relative-time"` so the e2e visual lane can mask it — relative
 * time is inherently non-deterministic and would otherwise flake byte/pixel
 * comparisons. Prefer this over inline formatDistanceToNow calls.
 */
export function RelativeTime({ iso, suffix = "" }: { iso: string; suffix?: string }) {
  return (
    <time dateTime={iso} data-testid="relative-time">
      {formatDistanceToNow(new Date(iso))}
      {suffix}
    </time>
  );
}
