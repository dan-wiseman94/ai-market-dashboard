import { Link } from "react-router-dom";
import { useThreads } from "@/hooks/useThread";
import { formatDistanceToNow } from "date-fns";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";

export default function ThreadsPage() {
  const { data, isLoading } = useThreads();
  const threads = data ?? [];

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Threads</h1>
        <Link to="/snapshot" className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-sm">
          + Snapshot
        </Link>
      </div>
      {isLoading ? (
        <SkeletonRows rows={4} />
      ) : threads.length === 0 ? (
        <EmptyState
          title="No threads yet"
          body="Capture a snapshot and pin it to start a consultation."
        />
      ) : (
        <ul className="space-y-1">
          {threads.map((t) => (
            <li key={t.id} data-testid={`thread-row-${t.id}`} className="p-3 rounded border border-slate-800 flex justify-between">
              <Link to={`/threads/${t.id}`} className="hover:underline">
                <div className="font-medium">{t.title || `Thread #${t.id}`}</div>
                <div className="text-xs text-slate-500">
                  {t.kind} · {t.profile?.name ?? "no profile"} · {formatDistanceToNow(new Date(t.created_at))} ago
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
