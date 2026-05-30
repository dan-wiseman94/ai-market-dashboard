import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { createChart, IChartApi, ISeriesApi } from "lightweight-charts";
import { useTheme, type ResolvedTheme } from "@/hooks/useTheme";
import { lightweightLayout } from "@/lib/chartTheme";

export interface PriceLineSpec {
  price: number;
  color: string;
  title: string;
}

export interface ChartProps {
  ticker: string;
  timeframe: string;
  bars: number;
  theme?: ResolvedTheme;
  onReady?: () => void;
  priceLines?: PriceLineSpec[];
}

interface OHLCBar {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface OHLCResponse {
  ticker: string;
  timeframe: string;
  bars: OHLCBar[];
}

export default function Chart({ ticker, timeframe, bars, theme, onReady, priceLines }: ChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const { resolved } = useTheme();
  const activeTheme = theme ?? resolved;

  const { data, isError } = useQuery<OHLCResponse>({
    queryKey: ["ohlc", ticker, timeframe, bars],
    queryFn: async () => {
      const r = await fetch(
        `/api/market/ohlc/?ticker=${encodeURIComponent(ticker)}&timeframe=${timeframe}&bars=${bars}`,
      );
      if (!r.ok) throw new Error(`OHLC ${r.status}`);
      return r.json();
    },
    retry: false,
  });

  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;
    chartRef.current = createChart(containerRef.current, {
      autoSize: true,
      ...lightweightLayout(activeTheme),
    });
    seriesRef.current = chartRef.current.addCandlestickSeries();
    return () => {
      chartRef.current?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    chartRef.current?.applyOptions(lightweightLayout(activeTheme));
  }, [activeTheme]);

  useEffect(() => {
    if (data?.bars?.length && seriesRef.current) {
      seriesRef.current.setData(
        data.bars.map((b) => ({
          time: Math.floor(new Date(b.ts).getTime() / 1000) as never,
          open: b.open, high: b.high, low: b.low, close: b.close,
        })),
      );
      chartRef.current?.timeScale().fitContent();
      onReady?.();
    } else if (data || isError) {
      // Settled with no bars (empty success) or an error: still signal ready so
      // the headless capture doesn't hang waiting for data that never arrives.
      onReady?.();
    }
  }, [data, isError, onReady]);

  useEffect(() => {
    if (!seriesRef.current || !priceLines?.length) return;
    for (const line of priceLines) {
      seriesRef.current.createPriceLine({
        price: line.price,
        color: line.color,
        lineWidth: 1,
        lineStyle: 2, // dashed
        axisLabelVisible: true,
        title: line.title,
      });
    }
    // Price lines are one-shot decorations — no cleanup needed when priceLines
    // reference changes (e.g. a new series would be created on remount).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [priceLines]);

  const noData = isError || (!!data && !data.bars?.length);

  // #chart-root is a React-controlled wrapper; the chart mounts into an inner
  // div so lightweight-charts' imperative canvas never fights React over the
  // no-data overlay. The headless capture screenshots #chart-root, so the
  // overlay is included.
  return (
    <div
      id="chart-root"
      style={{ position: "relative", width: "100%", height: "100%", minHeight: 360 }}
    >
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      {noData && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#888",
            fontSize: 14,
            pointerEvents: "none",
          }}
        >
          No price data
        </div>
      )}
    </div>
  );
}
