import { Link } from "react-router-dom";
import { useExportThread } from "@/hooks/useExport";

export default function ThreadExportButton({ threadId }: { threadId: number }) {
  const m = useExportThread();
  return (
    <div className="flex items-center gap-2">
      <button
        className="ledger-ghost py-1 px-2.5 text-[11px] font-mono uppercase tracking-wider"
        disabled={m.isPending}
        onClick={() => m.mutate(threadId)}
      >
        {m.isPending ? "Queuing…" : "↓ Export"}
      </button>
      {m.data && (
        <Link
          to="/settings/export"
          className="text-[11px] font-mono text-copper-300 hover:text-copper-200 transition-colors underline-offset-2 hover:underline"
        >
          View in Exports
        </Link>
      )}
    </div>
  );
}
