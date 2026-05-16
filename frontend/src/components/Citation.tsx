export interface CitationProps {
  index: number;
  source: string;
  title: string;
  snippet?: string;
}

export function Citation({ index, source, title, snippet }: CitationProps) {
  const isUrl = source.startsWith("http");
  const label = `${title}${snippet ? `: ${snippet}` : ""}`;
  const inner = (
    <sup
      data-testid={`citation-${index}`}
      className="ml-0.5 text-sky-400 cursor-help"
      aria-label={label}
      title={label}
    >
      [{index}]
    </sup>
  );
  return isUrl ? (
    <a href={source} target="_blank" rel="noreferrer">{inner}</a>
  ) : (
    inner
  );
}
