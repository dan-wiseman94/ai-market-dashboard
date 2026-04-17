import { useSearchParams } from "react-router-dom";
import Chart from "../components/Chart";

export default function RenderChart() {
  const [params] = useSearchParams();
  const ticker = params.get("ticker") ?? "SPY";
  const timeframe = params.get("timeframe") ?? "5m";
  const bars = Number(params.get("bars") ?? "60");

  function onReady() {
    document.body.dataset.renderReady = "true";
  }

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0a0a0a" }}>
      <Chart ticker={ticker} timeframe={timeframe} bars={bars} onReady={onReady} />
    </div>
  );
}
