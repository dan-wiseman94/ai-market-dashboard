import { useTrackRecord } from "@/hooks/useAnalytics";

export function TrackRecordHint({
  ticker,
  direction,
  conviction,
}: {
  ticker: string;
  direction?: string;
  conviction?: number;
}) {
  const { data } = useTrackRecord(ticker, direction, conviction);
  if (!data?.available || !data.record) return null;
  const r = data.record;
  const hr = r.hit_rate != null ? ` (${Math.round(r.hit_rate * 100)}%)` : "";
  return (
    <div
      className="text-[12px] text-ink-400 border border-rule rounded px-2 py-1.5"
      data-testid="track-record-hint"
    >
      <span className="text-copper-300">Your {r.ticker} track record:</span>{" "}
      {r.closed_n} closed — {r.counts.win}W / {r.counts.loss}L{hr}.
      {r.slice
        ? ` Conviction-${r.slice.conviction} ${r.slice.direction}: ${r.slice.correct}/${r.slice.n} correct.`
        : ""}
    </div>
  );
}
