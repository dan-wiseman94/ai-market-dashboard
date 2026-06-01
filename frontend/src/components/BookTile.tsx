import { Link } from "react-router-dom";

export interface DashboardBook {
  hhi: number | null;
  alignment: string | null;
  as_of: string | null;
}

export function BookTile({ book }: { book: DashboardBook }) {
  return (
    <Link to="/book" className="block rounded border border-rule p-4 hover:bg-ink/5">
      <div className="text-xs uppercase tracking-wide text-ink/60">Book risk</div>
      {book.alignment ? (
        <>
          <div className={`mt-1 text-xl font-bold ${book.alignment === "misaligned" ? "text-copper" : "text-ink"}`}>
            {book.alignment}
          </div>
          {book.hhi != null && <div className="mt-1 text-sm text-ink/70">HHI {book.hhi.toFixed(2)}</div>}
        </>
      ) : (
        <div className="mt-1 text-sm text-ink/60">No snapshot yet</div>
      )}
    </Link>
  );
}
