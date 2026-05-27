import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { createChart, IChartApi, ISeriesApi } from "lightweight-charts";
import { useTheme, type ResolvedTheme } from "@/hooks/useTheme";
import { lightweightLayout } from "@/lib/chartTheme";

export interface ChartProps {
  ticker: string;
  timeframe: string;
  bars: number;
  theme?: ResolvedTheme;
  onReady?: () => void;
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

export default function Chart({ ticker, timeframe, bars, theme, onReady }: ChartProps) {
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
    } else if (isError) {
      onReady?.();
    }
  }, [data, isError, onReady]);

  return <div id="chart-root" ref={containerRef} style={{ width: "100%", height: "100%", minHeight: 360 }} />;
}
