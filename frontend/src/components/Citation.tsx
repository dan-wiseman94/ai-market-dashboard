export interface CitationProps {
  index: number;
  source: string;
  title: string;
  snippet?: string;
}

/**
 * Parse a citation `source` and return it only when it is a real web link.
 *
 * `source` is model-influenced text: it arrives on the citation event straight
 * from the provider's annotation (a search_result source, a web-search url, or
 * "" for a document citation). A `startsWith("http")` test accepts lookalike
 * schemes — `httpevil://…`, `httpx:…` — and a naive "is it a link" test accepts
 * `javascript:`/`data:`, so parse the URL and allow only the http(s) protocols.
 * Anything else (including the unresolvable `news://<feed-id>` pseudo-URI) has
 * no navigable target and renders as a bare marker.
 */
// eslint-disable-next-line react-refresh/only-export-components -- pure guard, co-located with the component it protects and imported by its test
export function httpHref(source: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(source);
  } catch {
    return null; // relative / malformed / empty — not a link
  }
  return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : null;
}

export function Citation({ index, source, title, snippet }: CitationProps) {
  const href = httpHref(source);
  const label = `${title}${snippet ? `: ${snippet}` : ""}`;
  const inner = (
    <sup
      data-testid={`citation-${index}`}
      className="ml-0.5 text-sky-700 dark:text-sky-400 cursor-help"
      aria-label={label}
      title={label}
    >
      [{index}]
    </sup>
  );
  return href ? (
    <a href={href} target="_blank" rel="noreferrer">{inner}</a>
  ) : (
    inner
  );
}
