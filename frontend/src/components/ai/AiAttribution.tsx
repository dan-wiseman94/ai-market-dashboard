import { providerLabel } from "@/api/ai";
import { usd } from "@/utils/format";

type Props = {
  provider?: string | null;
  model?: string | null;
  cost?: string | number | null;
  /** e.g. "override" / "profile" — rendered dimmed in parentheses. */
  qualifier?: string;
  className?: string;
};

/** `Provider · model-id · $cost (qualifier)` as a mono ledger pill. */
export default function AiAttribution({ provider, model, cost, qualifier, className }: Props) {
  if (!provider && !model) return null;
  const parts = [provider ? providerLabel(provider) : null, model || null, cost != null && cost !== "" ? usd(cost) : null]
    .filter(Boolean) as string[];
  return (
    <span data-testid="ai-attribution" className={`ledger-pill font-mono ${className ?? ""}`}>
      {parts.join(" · ")}
      {qualifier && <span className="text-ink-500"> ({qualifier})</span>}
    </span>
  );
}
