import type { SnapshotListRow } from "@/api/snapshots";
import { RelativeTime } from "@/components/RelativeTime";

type Props = {
  rows: SnapshotListRow[];
  selected: number[];
  onToggle: (id: number) => void;
};

export default function SnapshotTable({ rows, selected, onToggle }: Props) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-ink-400 text-left border-b border-rule">
          <tr>
            <th className="py-2 pr-3 w-6" aria-label="Select" />
            <th className="py-2 pr-4">Ticker</th>
            <th className="py-2 pr-4">Objective</th>
            <th className="py-2 pr-4">Profile</th>
            <th className="py-2 pr-4">Source</th>
            <th className="py-2 pr-4">Sections</th>
            <th className="py-2 pr-4">Status</th>
            <th className="py-2">Captured</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const isSelected = selected.includes(row.id);
            return (
              <tr
                key={row.id}
                className={[
                  "border-b border-rule transition-colors cursor-pointer",
                  isSelected ? "bg-copper-900/20" : "hover:bg-ink-900/30",
                ].join(" ")}
                onClick={() => onToggle(row.id)}
              >
                <td className="py-2 pr-3">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => onToggle(row.id)}
                    onClick={(e) => e.stopPropagation()}
                    aria-label={`Select snapshot ${row.id}`}
                    className="accent-copper-500"
                  />
                </td>
                <td className="py-2 pr-4 font-mono font-medium text-copper-300">
                  {row.primary_ticker ?? "—"}
                </td>
                <td className="py-2 pr-4 max-w-xs truncate text-ink-200">
                  {row.objective || "—"}
                </td>
                <td className="py-2 pr-4 text-ink-400">{row.profile_name}</td>
                <td className="py-2 pr-4 text-ink-400 capitalize">{row.source}</td>
                <td className="py-2 pr-4 text-ink-400 font-mono text-xs">
                  {row.section_kinds.join(", ") || "—"}
                </td>
                <td className="py-2 pr-4">
                  <span
                    className={[
                      "px-1.5 py-0.5 rounded text-xs font-mono",
                      row.status === "ready"
                        ? "bg-emerald-900/40 text-emerald-400"
                        : row.status === "failed"
                          ? "bg-rose-900/40 text-rose-400"
                          : "bg-ink-800 text-ink-400",
                    ].join(" ")}
                  >
                    {row.status}
                  </span>
                </td>
                <td className="py-2 text-ink-500 text-xs whitespace-nowrap">
                  <RelativeTime iso={row.captured_at} suffix=" ago" />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
