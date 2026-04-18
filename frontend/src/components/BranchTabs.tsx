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
    <div className="flex gap-1 border-b border-slate-800 text-xs">
      {branches.map((b) => (
        <button
          key={b.id}
          onClick={() => onSelect(b.id)}
          className={`px-3 py-1.5 border-b-2 ${
            activeId === b.id ? "border-emerald-500 text-emerald-300" : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          {b.label}
          {b.cost !== undefined ? (
            <span data-testid={`branch-cost-${b.id}`} className="ml-2 font-mono text-[11px] text-slate-300">
              ${b.cost.toFixed(4)}
            </span>
          ) : b.status === "streaming" ? (
            <span
              data-testid={`branch-cost-pending-${b.id}`}
              aria-label="calculating cost"
              className="ml-2 inline-block w-2 h-2 rounded-full bg-slate-600 animate-pulse align-middle"
            />
          ) : null}
          <span className="ml-1 text-slate-600">
            {b.status === "failed" ? "✗" : ""}
          </span>
        </button>
      ))}
    </div>
  );
}
