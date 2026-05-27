// Single source of truth for turning a backend calendar status into the
// three session states the UI shows. The nav badge and the dashboard hero both
// derive from this so they can never disagree (they used to: the badge read the
// authoritative backend while the hero used a divergent client-side clock).

export type SessionKind = "open" | "extended" | "closed";

/** Map a market's `{is_open, phase}` to a session kind. */
export function sessionKind(status: { is_open: boolean; phase?: string }): SessionKind {
  if (status.is_open) return "open";
  if (status.phase === "premarket" || status.phase === "postmarket") return "extended";
  return "closed";
}

export const SESSION_LABEL: Record<SessionKind, string> = {
  open: "Open",
  extended: "Extended Hours",
  closed: "Closed",
};
