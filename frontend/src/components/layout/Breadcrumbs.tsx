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
    <nav
      aria-label="Breadcrumb"
      className="px-6 py-2 text-[11px] font-mono text-ink-500 border-b border-rule flex items-center"
    >
      <span className="text-copper-500/70 mr-2" aria-hidden>◈</span>
      {crumbs.map((c, i) => (
        <span key={c.match.id} className="inline-flex items-center">
          {i > 0 && <span className="mx-2 text-ink-600" aria-hidden>/</span>}
          {i < crumbs.length - 1 ? (
            <Link
              to={c.match.pathname}
              className="uppercase tracking-loose2 hover:text-copper-300 transition-colors duration-150"
            >
              {c.label}
            </Link>
          ) : (
            <span className="uppercase tracking-loose2 text-ink-200">{c.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
