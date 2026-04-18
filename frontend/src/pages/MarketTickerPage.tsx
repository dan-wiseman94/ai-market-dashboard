import { useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Chart from "@/components/Chart";
import ChartCaptureButton from "@/components/ChartCaptureButton";
import OptionChainTable from "@/components/OptionChainTable";
import NewsFeed from "@/components/NewsFeed";

export default function MarketTickerPage() {
  const { ticker = "SPY" } = useParams<{ ticker: string }>();
  const [params] = useSearchParams();
  const timeframe = params.get("timeframe") ?? "5m";
  const bars = Number(params.get("bars") ?? "120");
  const chartContainer = useRef<HTMLDivElement | null>(null);

  const { data: chain } = useQuery({
    queryKey: ["chain", ticker],
    queryFn: () => fetch(`/api/market/chain/?ticker=${ticker}`).then((r) => r.json()),
  });

  const { data: news } = useQuery({
    queryKey: ["news", ticker],
    queryFn: () => fetch(`/api/market/news/?tickers=${ticker}`).then((r) => r.json()),
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, padding: 16 }}>
      <h1 style={{ margin: 0 }}>{ticker.toUpperCase()}</h1>

      <div ref={chartContainer} style={{ position: "relative", height: 400, background: "#0a0a0a" }}>
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
