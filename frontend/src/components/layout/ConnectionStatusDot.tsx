import { useHealth } from "@/hooks/useHealth";

export default function ConnectionStatusDot() {
  const state = useHealth();
  const map = {
    ok:      { color: "var(--gain-400)",   label: "Live",        pulse: true  },
    loading: { color: "var(--copper-400)", label: "Connecting…", pulse: true  },
    down:    { color: "var(--loss-400)",   label: "Offline",     pulse: false },
  } as const;
  const cur = map[state];

  return (
    <span
      title={cur.label}
      aria-label={`Connection: ${cur.label}`}
      data-testid="connection-status-dot"
      className="inline-flex items-center gap-2 select-none"
    >
      <span
        className="relative inline-block h-1.5 w-1.5 rounded-full"
        style={{ background: cur.color, color: cur.color }}
      >
        {cur.pulse && (
          <span
            aria-hidden
            className="absolute inset-0 rounded-full ledger-pulse"
            style={{ color: cur.color }}
          />
        )}
      </span>
      <span className="text-[10px] uppercase tracking-loose2" style={{ color: cur.color }}>
        {cur.label}
      </span>
    </span>
  );
}
