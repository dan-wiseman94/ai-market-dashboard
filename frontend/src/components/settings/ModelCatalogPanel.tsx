import { PROVIDER_IDS, PROVIDER_LABEL } from "@/api/ai";
import { fmtTokens } from "@/components/ai/ModelFacts";
import { SkeletonRows } from "@/components/Skeleton";
import { useCatalog } from "@/hooks/useCatalog";

const money = (n: number) => `$${n.toFixed(2)}`;

/** The price/context/budget table the catalog drives — the reference behind every
 * cost estimate, cap and snapshot payload budget in the app. */
export default function ModelCatalogPanel() {
  const { models, defaultFor, isLoading } = useCatalog();

  return (
    <section className="ledger-surface p-5" aria-labelledby="model-catalog-heading">
      <div className="flex items-end justify-between gap-4 max-sm:flex-col max-sm:items-start">
        <div>
          <p className="ledger-eyebrow">Reference</p>
          <h3 id="model-catalog-heading" className="font-display text-[1.05rem] text-ink-50">
            Model catalog
          </h3>
        </div>
        <p className="max-w-sm text-[11px] text-ink-400 sm:text-right">
          Prices are per million tokens. The payload budget is how much snapshot the
          serializer sends before it starts pruning sections.
        </p>
      </div>

      {isLoading ? (
        <div className="mt-4">
          <SkeletonRows rows={4} />
        </div>
      ) : (
        PROVIDER_IDS.map((p) => {
          const rows = models.filter((m) => m.provider === p);
          if (rows.length === 0) return null;
          return (
            <div key={p} className="mt-5 min-w-0 overflow-x-auto">
              <p className="mb-2 font-mono text-[10px] uppercase tracking-loose2 text-copper-400">
                {PROVIDER_LABEL[p]}
              </p>
              <table className="w-full text-[12px]">
                <thead>
                  <tr className="text-left text-ink-400">
                    <th className="py-1 pr-3 font-normal">Model</th>
                    <th className="py-1 pr-3 text-right font-normal">Input</th>
                    <th className="py-1 pr-3 text-right font-normal">Cached</th>
                    <th className="py-1 pr-3 text-right font-normal">Output</th>
                    <th className="py-1 pr-3 text-right font-normal">Context</th>
                    <th className="py-1 pr-3 text-right font-normal">Payload</th>
                    <th className="py-1 font-normal">Vision</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((m) => (
                    <tr
                      key={m.id}
                      data-testid={`catalog-row-${m.id}`}
                      className="border-t border-rule-soft align-top"
                    >
                      <td className="py-1.5 pr-3">
                        <div className="flex items-center gap-2 text-ink-100">
                          {m.name}
                          {defaultFor(p) === m.id && (
                            <span className="ledger-pill" data-tone="copper">default</span>
                          )}
                        </div>
                        <div className="font-mono text-[11px] text-ink-400">{m.id}</div>
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {money(m.input_per_mtok)}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {money(m.cached_per_mtok)}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {money(m.output_per_mtok)}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {fmtTokens(m.context_window)}
                      </td>
                      <td className="py-1.5 pr-3 text-right tabular-nums">
                        {m.max_payload_tokens != null ? fmtTokens(m.max_payload_tokens) : "40k"}
                      </td>
                      <td className="py-1.5 text-ink-300">{m.supports_vision ? "yes" : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })
      )}

      <p className="mt-4 border-t border-rule-soft pt-3 text-[11px] text-ink-400">
        These prices drive cost estimates and caps. A model id that is not listed is billed
        at its provider&apos;s top rate and capped at a 40k-token snapshot payload — add it
        to the catalog first.
      </p>
    </section>
  );
}
