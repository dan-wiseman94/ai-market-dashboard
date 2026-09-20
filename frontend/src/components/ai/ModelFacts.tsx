import { useCatalog } from "@/hooks/useCatalog";

/** 1_000_000 → "1M", 1_050_000 → "1.05M", 150_000 → "150k". */
export function fmtTokens(n: number): string {
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return `${Number.isInteger(m) ? m : m.toFixed(2).replace(/0+$/, "")}M`;
  }
  return `${Math.round(n / 1000)}k`;
}

const money = (n: number) => `$${n.toFixed(2)}`;

export default function ModelFacts({ provider, modelId }: { provider: string; modelId: string }) {
  const { byId, defaultFor } = useCatalog();
  if (!modelId) return null;
  const m = byId(modelId);
  const base = "font-mono text-[11px] text-ink-400 tabular-nums flex flex-wrap items-center gap-x-1.5";
  if (!m || m.provider !== provider) {
    return (
      <p data-testid="model-facts" className={base}>
        {provider === "local"
          ? "local model — no API cost · 40k payload budget"
          : "not in catalog — billed at the provider's top rate · 40k payload budget"}
      </p>
    );
  }
  const parts = [
    `${money(m.input_per_mtok)} in`,
    `${money(m.cached_per_mtok)} cached`,
    `${money(m.output_per_mtok)} out per MTok`,
    `${fmtTokens(m.context_window)} ctx`,
    m.max_payload_tokens != null ? `${fmtTokens(m.max_payload_tokens)} payload` : null,
    m.supports_vision ? "vision" : null,
  ].filter(Boolean) as string[];
  return (
    <p data-testid="model-facts" className={base}>
      {parts.map((p, i) => (
        <span key={p}>{i > 0 && <span className="text-ink-600"> · </span>}{p}</span>
      ))}
      {defaultFor(provider) === m.id && (
        <span className="ledger-pill ml-1" data-tone="copper">default</span>
      )}
    </p>
  );
}
