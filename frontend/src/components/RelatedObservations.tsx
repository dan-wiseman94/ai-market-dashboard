import { Link } from "react-router-dom";
import { useRelated } from "@/hooks/useRecall";
import { Skeleton } from "@/components/Skeleton";

interface RelatedObservationsProps {
  kind: string;
  id: number;
}

export function RelatedObservations({ kind, id }: RelatedObservationsProps) {
  const { data, isLoading } = useRelated(kind, id);
  const hits = data?.results ?? [];

  if (isLoading) {
    return (
      <aside className="mt-8 ledger-surface rounded-sm px-4 py-4">
        <div className="ledger-eyebrow mb-3">Related</div>
        <div className="space-y-2">
          <Skeleton where="related-1" className="h-5 w-full" />
          <Skeleton where="related-2" className="h-5 w-3/4" />
          <Skeleton where="related-3" className="h-5 w-5/6" />
        </div>
      </aside>
    );
  }

  if (hits.length === 0) {
    return null;
  }

  return (
    <aside className="mt-8 ledger-surface rounded-sm px-4 py-4" data-testid="related-observations">
      <div className="ledger-eyebrow mb-3 flex items-center gap-2">
        <span>You noted this before</span>
        <span className="flex-1 h-px bg-rule" />
        <span className="font-mono text-[10px] text-ink-500">{hits.length}</span>
      </div>
      <ul className="space-y-2">
        {hits.map((hit) => (
          <li key={`${hit.kind}-${hit.object_id}`} className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <span className="font-mono text-[10px] uppercase tracking-wider text-ink-500">
                {hit.kind}
              </span>
              {hit.tickers.length > 0 && (
                <span className="font-mono text-[10px] text-copper-500">
                  {hit.tickers.join(" · ")}
                </span>
              )}
              {hit.source_created_at && (
                <span className="font-mono text-[10px] text-ink-600 ml-auto">
                  {new Date(hit.source_created_at).toLocaleDateString()}
                </span>
              )}
            </div>
            <Link
              to={hit.link}
              className="text-[12px] text-ink-300 hover:text-ink-100 transition-colors line-clamp-2"
            >
              {hit.snippet || hit.link}
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}
