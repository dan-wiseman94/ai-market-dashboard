import { usd } from "@/utils/format";

type BranchTab = {
  id: number;
  label: string;
  status: "streaming" | "done" | "failed";
  cost?: number;
};

type Props = {
  branches: BranchTab[];
  activeId: number | null;
  onSelect: (id: number) => void;
};

export default function BranchTabs({ branches, activeId, onSelect }: Props) {
  if (branches.length === 0) return null;
  return (
    <div className="relative flex gap-0 border-b border-rule">
      {branches.map((b) => {
        const active = activeId === b.id;
        return (
          <button
            key={b.id}
            onClick={() => onSelect(b.id)}
            className={[
              "relative group px-4 py-2.5 flex items-center gap-3 transition-colors duration-150 ease-ledger",
              active ? "text-copper-200" : "text-ink-400 hover:text-ink-100",
            ].join(" ")}
          >
            <span
              aria-hidden
              className={[
                "absolute left-0 right-0 -bottom-[1px] h-[2px] transition-all duration-300 ease-ledger",
                active ? "bg-copper-400 opacity-100" : "bg-copper-400 opacity-0 group-hover:opacity-30",
              ].join(" ")}
            />
            <span className="font-mono text-[11px] uppercase tracking-wider">
              {b.label}
            </span>
            {b.cost !== undefined ? (
              <span
                data-testid={`branch-cost-${b.id}`}
                className="font-mono text-[11px] tabular-nums text-ink-300"
              >
                {usd(b.cost)}
              </span>
            ) : b.status === "streaming" ? (
              <span
                data-testid={`branch-cost-pending-${b.id}`}
                aria-label="calculating cost"
                className="inline-flex items-center gap-1 font-mono text-[10px] text-copper-400"
              >
                <span className="inline-block h-1 w-1 rounded-full bg-copper-400 ledger-pulse" />
                streaming
              </span>
            ) : null}
            {b.status === "failed" && (
              <span className="font-mono text-[10px] text-loss">✗</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
