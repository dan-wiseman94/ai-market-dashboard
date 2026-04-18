import { Link, useMatches, type UIMatch } from "react-router-dom";

type CrumbFn = (m: UIMatch) => string;
type Handle = { crumb?: string | CrumbFn };

function resolveCrumb(match: UIMatch): string | null {
  const h = match.handle as Handle | undefined;
  if (!h?.crumb) return null;
  if (typeof h.crumb === "string") return h.crumb;
  return h.crumb(match);
}

export default function Breadcrumbs() {
  const matches = useMatches();
  const crumbs = matches
    .map((m) => ({ match: m, label: resolveCrumb(m) }))
    .filter((c): c is { match: UIMatch; label: string } => !!c.label);

  if (crumbs.length === 0) return null;

  return (
    <nav aria-label="Breadcrumb" className="px-4 py-1.5 text-xs text-slate-500 border-b border-slate-900">
      {crumbs.map((c, i) => (
        <span key={c.match.id}>
          {i > 0 && <span className="mx-1.5">/</span>}
          {i < crumbs.length - 1 ? (
            <Link to={c.match.pathname} className="hover:text-slate-300">{c.label}</Link>
          ) : (
            <span className="text-slate-300">{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
