type Props = { mode: "full" | "diff"; structured: boolean; consensus: boolean; use_batch: boolean; investigate?: boolean };

/** A schedule's AI mode as pills: payload shape, then each opt-in flag. */
export default function ModeBadges({ mode, structured, consensus, use_batch, investigate }: Props) {
  const flags = [structured && "structured", consensus && "consensus", use_batch && "batch", investigate && "investigate"]
    .filter(Boolean) as string[];
  return (
    <span className="inline-flex flex-wrap gap-1" data-testid="mode-badges">
      <span className="ledger-pill">{mode}</span>
      {flags.map((f) => <span key={f} className="ledger-pill" data-tone="copper">{f}</span>)}
    </span>
  );
}
