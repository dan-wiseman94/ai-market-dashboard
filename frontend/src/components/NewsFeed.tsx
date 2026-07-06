export interface NewsItem {
  id: number | string;
  headline: string;
  summary?: string;
  source?: string;
  url: string;
  datetime: number;
}

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleString();
}

export default function NewsFeed({ items }: { items: NewsItem[] }) {
  if (!items.length) {
    return <div style={{ padding: 12, color: "var(--ink-400)" }}>No headlines.</div>;
  }
  const sorted = [...items].sort((a, b) => b.datetime - a.datetime).slice(0, 15);
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
      {sorted.map((it) => (
        <li key={it.id} style={{ padding: "8px 12px", borderBottom: "1px solid var(--rule-soft)" }}>
          <div style={{ fontSize: 11, color: "var(--ink-400)" }}>
            {fmt(it.datetime)} — {it.source ?? "?"}
          </div>
          <a
            href={it.url}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--copper-300)", fontSize: 14 }}
          >{it.headline}</a>
          {it.summary && <div style={{ fontSize: 12, color: "var(--ink-300)", marginTop: 2 }}>{it.summary}</div>}
        </li>
      ))}
    </ul>
  );
}
