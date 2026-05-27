import type { ResolvedTheme } from "@/hooks/useTheme";

/** lightweight-charts layout/grid options. */
export function lightweightLayout(theme: ResolvedTheme) {
  const c =
    theme === "light"
      ? { background: "#f5f2ea", textColor: "#2e2a22", grid: "#e2dccd" }
      : { background: "#0a0a0a", textColor: "#d0d0d0", grid: "#1a1a1a" };
  return {
    layout: { background: { color: c.background }, textColor: c.textColor },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
  };
}

export interface RechartsColors {
  axis: string;
  cursor: string;
  tickText: string;
  dotStroke: string;
  heatmapEmpty: string;
}

export function rechartsColors(theme: ResolvedTheme): RechartsColors {
  return theme === "light"
    ? {
        axis: "rgba(160,111,44,0.30)",
        cursor: "rgba(160,111,44,0.45)",
        tickText: "#5c5648",
        dotStroke: "#f5f2ea",
        heatmapEmpty: "rgba(0,0,0,0.04)",
      }
    : {
        axis: "rgba(200,150,88,0.15)",
        cursor: "rgba(200,150,88,0.40)",
        tickText: "#9ea3b3",
        dotStroke: "#0b0d12",
        heatmapEmpty: "rgba(255,255,255,0.04)",
      };
}
