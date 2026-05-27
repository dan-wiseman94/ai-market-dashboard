import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import Chart from "@/components/Chart";

function signalRenderReady(): void {
  document.body.dataset.renderReady = "true";
}

export default function RenderChart() {
  const [params] = useSearchParams();
  const ticker = params.get("ticker") ?? "SPY";
  const timeframe = params.get("timeframe") ?? "5m";
  const bars = Number(params.get("bars") ?? "60");

  // Deterministic capture: the headless context has no saved preference, so
  // force dark regardless of what the bootstrap resolved.
  useEffect(() => {
    const r = document.documentElement;
    r.classList.add("dark");
    r.classList.remove("light");
  }, []);

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0a0a0a" }}>
      <Chart ticker={ticker} timeframe={timeframe} bars={bars} theme="dark" onReady={signalRenderReady} />
    </div>
  );
}
