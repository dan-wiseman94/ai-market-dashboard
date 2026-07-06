import { useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/api/client";
import Chart from "@/components/Chart";
import ChartCaptureButton from "@/components/ChartCaptureButton";
import OptionChainTable, { type ChainPayload } from "@/components/OptionChainTable";
import NewsFeed, { type NewsItem } from "@/components/NewsFeed";

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
