import { useMemo } from "react";
import Chart, { type PriceLineSpec } from "@/components/Chart";
import { Skeleton } from "@/components/Skeleton";
import { useOhlc } from "@/hooks/useOhlc";

// Hex values that lightweight-charts can consume directly (CSS vars can't be
// passed into the canvas; we use the same palette as the design tokens).
const GAIN_COLOR = "#4fb38a";  // --gain-400
const LOSS_COLOR = "#c55c62";  // --loss-400
const ENTRY_COLOR = "#d79642"; // --copper-400

export interface ThesisChartProps {
  ticker: string;
  entry?: number | string | null;
  target?: number | string | null;
  invalidation?: number | string | null;
}

function toNum(v: number | string | null | undefined): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export default function ThesisChart({ ticker, entry, target, invalidation }: ThesisChartProps) {
  const { data, isLoading, isError } = useOhlc(ticker, "1D", 90);

  const priceLines = useMemo<PriceLineSpec[]>(() => {
    const lines: PriceLineSpec[] = [];
    const t = toNum(target);
    const inv = toNum(invalidation);
    const ent = toNum(entry);
    if (t !== null) lines.push({ price: t, color: GAIN_COLOR, title: "Target" });
    if (inv !== null) lines.push({ price: inv, color: LOSS_COLOR, title: "Invalidation" });
    if (ent !== null) lines.push({ price: ent, color: ENTRY_COLOR, title: "Entry" });
    return lines;
  }, [target, invalidation, entry]);

  if (isLoading) {
    return (
      <Skeleton
        where="thesis-chart"
        className="w-full h-64"
      />
    );
  }

  if (isError || !data) {
    return null;
  }

  return (
    <div data-testid="thesis-chart" style={{ height: 280, position: "relative" }}>
      <Chart ticker={ticker} timeframe="1D" bars={90} priceLines={priceLines} />
    </div>
  );
}
