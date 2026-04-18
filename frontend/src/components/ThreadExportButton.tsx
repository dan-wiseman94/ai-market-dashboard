import { Link } from "react-router-dom";
import { useExportThread } from "@/hooks/useExport";

export default function ThreadExportButton({ threadId }: { threadId: number }) {
  const m = useExportThread();
  return (
    <div className="flex items-center gap-2">
      <button
        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs"
        disabled={m.isPending}
        onClick={() => m.mutate(threadId)}
      >
        {m.isPending ? "Queuing…" : "⇣ Export"}
      </button>
      {m.data && (
        <Link to="/settings/export" className="text-xs text-emerald-300 hover:underline">
          View in Exports
        </Link>
      )}
    </div>
  );
}
