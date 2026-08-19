import { useState } from "react";

import type { ThemeHealth } from "@/api/themes";
import { EmptyState } from "@/components/EmptyState";
import { SkeletonRows } from "@/components/Skeleton";
import { useCreateTheme, useDeleteTheme, useThemeHealth, useThemes } from "@/hooks/useThemes";
import { pctSigned } from "@/utils/format";

export default function ThemesPage() {
  const { data: themes = [], isLoading } = useThemes();
  const create = useCreateTheme();
  const del = useDeleteTheme();
  const [selected, setSelected] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [tickers, setTickers] = useState("");
  const { data: health } = useThemeHealth(selected);

  async function onCreate() {
    const list = tickers.split(/[,\s]+/).map((t) => t.trim()).filter(Boolean);
    if (!name.trim() || list.length === 0) return;
    const t = await create.mutateAsync({ name: name.trim(), tickers: list });
    setName("");
    setTickers("");
    setSelected(t.id);
  }

  return (
    <main className="p-6 max-w-4xl mx-auto space-y-5 ledger-fade-in">
      <h1 className="text-2xl font-semibold">Themes</h1>
      <p className="text-sm text-ink-400">
        Group tickers into narratives and read each narrative&rsquo;s health — participation,
        leadership, and relative strength vs the tape.
      </p>

      <div className="flex flex-wrap gap-2">
        <input
          aria-label="Theme name"
          placeholder="Narrative (e.g. AI-capex)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="rounded border border-rule px-3 py-2 text-sm"
        />
        <input
          aria-label="Theme tickers"
          placeholder="Tickers (NVDA, AMD, TSM)"
          value={tickers}
          onChange={(e) => setTickers(e.target.value)}
          className="flex-1 min-w-[12rem] rounded border border-rule px-3 py-2 text-sm"
        />
        <button
          onClick={onCreate}
          disabled={create.isPending}
          className="rounded bg-gain-500 hover:bg-gain-400 px-3 py-2 text-sm disabled:opacity-50"
        >
          Add theme
        </button>
      </div>

      {isLoading ? (
        <SkeletonRows rows={3} />
      ) : themes.length === 0 ? (
        <EmptyState title="No themes yet" body="Create one above to start tracking a narrative." />
      ) : (
        <ul className="space-y-1">
          {themes.map((t) => (
            <li key={t.id} className="flex items-center justify-between rounded border border-rule p-3">
              <button className="text-left hover:underline" onClick={() => setSelected(t.id)}>
                <span className="font-medium">{t.name}</span>{" "}
                <span className="text-xs text-ink-500">{t.tickers.join(" · ")}</span>
              </button>
              <button
                className="text-xs text-copper-400 hover:text-copper-300"
                onClick={() => {
                  del.mutate(t.id);
                  if (selected === t.id) setSelected(null);
                }}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected != null && health && <ThemeHealthCard health={health} />}
    </main>
  );
}

function ThemeHealthCard({ health }: { health: ThemeHealth }) {
  return (
    <section data-testid="theme-health" className="rounded border border-rule p-4 space-y-2">
      <h2 className="font-medium">Narrative health ({health.window_days}d)</h2>
      {health.breadth == null ? (
        <p className="text-sm text-ink-500">
          Not enough priced members ({health.coverage.priced}/{health.coverage.total}).
        </p>
      ) : (
        <>
          <p className="text-sm text-ink-300">
            Breadth <span className="font-medium">{(health.breadth * 100).toFixed(0)}%</span> up ·
            mean {pctSigned(health.mean_return_pct)} · relative strength{" "}
            <span className={(health.relative_strength ?? 0) >= 0 ? "text-gain-400" : "text-copper-400"}>
              {pctSigned(health.relative_strength)}
            </span>{" "}
            vs $SPX {pctSigned(health.spx_return_pct)}
          </p>
          {health.leadership && (
            <p className="text-sm text-ink-400">
              Leader {health.leadership.leader.ticker} {pctSigned(health.leadership.leader.return_pct)} ·
              laggard {health.leadership.laggard.ticker} {pctSigned(health.leadership.laggard.return_pct)}
            </p>
          )}
          <ul className="text-sm text-ink-400">
            {health.members.map((m) => (
              <li key={m.ticker}>
                {m.ticker}: {pctSigned(m.return_pct)}
                {m.above_theme ? " ↑" : m.return_pct != null ? " ↓" : ""}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
