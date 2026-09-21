import { useRef } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/client";
import Chart from "@/components/Chart";
import ChartCaptureButton from "@/components/ChartCaptureButton";
import OptionChainTable, { type ChainPayload } from "@/components/OptionChainTable";
import NewsFeed, { type NewsItem } from "@/components/NewsFeed";
import { useCoverage } from "@/hooks/useCoverage";
import { convictionLabel, STANCE_LABEL } from "@/lib/coverageStance";

/** The house view on this ticker, one line — the standing note is the context a
 * chart can't carry. A 404 means nothing has opened coverage here yet. */
function CoverageStrip({ ticker }: { ticker: string }) {
  const { data: note, isLoading, isError } = useCoverage(ticker);
  const to = `/coverage/${encodeURIComponent(ticker.toUpperCase())}`;
  if (isLoading) return null;
  return (
    <section style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
      <h2 style={{ fontSize: 16, margin: 0 }}>House view</h2>
      {isError || !note ? (
        <span style={{ fontSize: 13, color: "var(--ink-500)" }}>
          No note yet — <Link to={to}>open coverage</Link>.
        </span>
      ) : (
        <span style={{ fontSize: 13 }}>
          {STANCE_LABEL[note.stance]}, conviction {convictionLabel(note.conviction)} ·{" "}
          <Link to={to}>read the note</Link>
        </span>
      )}
    </section>
  );
}

export default function MarketTickerPage() {
  const { ticker = "SPY" } = useParams<{ ticker: string }>();
  const [params] = useSearchParams();
  const timeframe = params.get("timeframe") ?? "5m";
  const bars = Number(params.get("bars") ?? "120");
  const chartContainer = useRef<HTMLDivElement | null>(null);

  // Route through the shared api client so a 5xx throws ApiError (entering the
  // query error path + toast policy) instead of resolving an error body as data.
  const { data: chain } = useQuery({
    queryKey: ["chain", ticker],
    queryFn: () =>
      apiGet<ChainPayload | null>(`/api/market/chain/?ticker=${encodeURIComponent(ticker)}`),
  });

  const { data: news } = useQuery({
    queryKey: ["news", ticker],
    queryFn: () =>
      apiGet<{ items?: NewsItem[] } | null>(
        `/api/market/news/?tickers=${encodeURIComponent(ticker)}`,
      ),
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 16 }}>
      <h1 style={{ margin: 0 }}>{ticker.toUpperCase()}</h1>

      <CoverageStrip ticker={ticker} />

      <div ref={chartContainer} style={{ position: "relative", height: 400, background: "var(--ink-950)" }}>
        <Chart ticker={ticker} timeframe={timeframe} bars={bars} />
        <ChartCaptureButton targetRef={chartContainer} caption={`${ticker} ${timeframe}, ${bars} bars`} />
      </div>

      <section>
        <h2 style={{ fontSize: 16, margin: "8px 0" }}>Option chain</h2>
        <OptionChainTable payload={chain ?? null} />
      </section>

      <section>
        <h2 style={{ fontSize: 16, margin: "8px 0" }}>News</h2>
        <NewsFeed items={news?.items ?? []} />
      </section>
    </div>
  );
}
