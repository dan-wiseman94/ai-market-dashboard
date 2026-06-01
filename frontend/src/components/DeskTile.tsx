import { Link } from "react-router-dom";

export interface DashboardDesk { unread: number; latest: string | null }

export function DeskTile({ desk }: { desk: DashboardDesk }) {
  return (
    <Link to="/desk" className="block rounded border border-rule p-4 hover:bg-ink/5">
      <div className="text-xs uppercase tracking-wide text-ink/60">The Desk</div>
      {desk.unread > 0 ? (
        <>
          <div className="mt-1 text-xl font-bold text-copper">{desk.unread} new</div>
          {desk.latest && <div className="mt-1 text-sm text-ink/70">{desk.latest}</div>}
        </>
      ) : (
        <div className="mt-1 text-sm text-ink/60">No new flags</div>
      )}
    </Link>
  );
}
