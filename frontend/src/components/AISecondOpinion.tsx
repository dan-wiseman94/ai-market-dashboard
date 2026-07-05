import { useAIView } from "@/hooks/usePredictions";

const AGREEMENT: Record<string, { label: string; cls: string }> = {
  agree: { label: "agrees with your thesis", cls: "text-gain-400" },
  diverge: { label: "diverges from your thesis", cls: "text-loss-400" },
  partial: { label: "partially diverges", cls: "text-ink-300" },
};

/**
 * The AI's current live call on this ticker, reconciled against the
 * trader's thesis direction — a second opinion at decision time. Renders nothing
 * until the AI has an open prediction on the ticker.
 */
export function AISecondOpinion({ ticker, against }: { ticker: string; against?: string }) {
  const { data } = useAIView(ticker, against);
  if (!data?.has_view) return null;
  const conf = data.confidence != null ? ` (${Math.round(data.confidence * 100)}%)` : "";
  const horizon = data.horizon_days != null ? `, ${data.horizon_days}d` : "";
  const agree = data.agreement ? AGREEMENT[data.agreement] : null;
  return (
    <div
      className="mt-2 rounded border border-rule px-2 py-1.5 text-[12px] text-ink-400"
      data-testid="ai-second-opinion"
    >
      <span className="text-copper-300">AI's current call on {data.ticker}:</span>{" "}
      <span className="text-ink-200">{data.direction}</span>
      {conf}
      {horizon}.
      {agree ? (
        <>
          {" "}
          The AI <span className={agree.cls}>{agree.label}</span>.
        </>
      ) : null}
    </div>
  );
}
