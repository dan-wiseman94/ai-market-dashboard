type Props = {
  branches: { id: number; label: string; status: "streaming" | "done" | "failed" }[];
  activeId: number | null;
  onSelect: (id: number) => void;
};

export default function BranchTabs({ branches, activeId, onSelect }: Props) {
  if (branches.length <= 1) return null;
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
          <span className="ml-1 text-slate-600">
            {b.status === "streaming" ? "…" : b.status === "failed" ? "✗" : ""}
          </span>
        </button>
      ))}
    </div>
  );
}
