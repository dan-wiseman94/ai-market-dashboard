import { Link } from "react-router-dom";
import { useParams } from "react-router-dom";
import { useThesis, useUpdateThesis } from "@/hooks/useTheses";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { ThesisMasthead } from "./thesis-detail/ThesisMasthead";
import { ThesisFields } from "./thesis-detail/ThesisFields";
import { SourceLinks } from "./thesis-detail/SourceLinks";
import { CloseThesisForm } from "./thesis-detail/CloseThesisForm";
import { PostMortemsSection } from "./thesis-detail/PostMortemsSection";
import Toggle from "@/components/ui/Toggle";
import type { Thesis } from "@/api/thesis";
import { TrackRecordHint } from "@/components/TrackRecordHint";
import { usePortfolioPositions } from "@/hooks/usePortfolio";

function PriceGuardToggle({ thesis }: { thesis: Thesis }) {
  const hasTargetOrInvalidation =
    thesis.target_price != null || thesis.invalidation_price != null;
  const hasProfile = thesis.profile_id != null;
  const canEnable = hasTargetOrInvalidation && hasProfile;
  const update = useUpdateThesis();

  const disabledReason = !hasTargetOrInvalidation
    ? "Set a target or invalidation price to enable"
    : !hasProfile
      ? "Attach a profile to enable"
      : undefined;

  return (
    <section className="mb-8 pb-6 border-b border-rule">
      <h2 className="ledger-eyebrow mb-3">Price guard</h2>
      <div className="flex items-center gap-3">
        <Toggle
          id="guard-toggle"
          label="Price guard"
          checked={thesis.guard_enabled}
          onChange={(next) => update.mutate({ id: thesis.id, body: { guard_enabled: next } })}
          disabled={!canEnable || update.isPending}
        />
        <label
          htmlFor="guard-toggle"
          className="text-sm text-ink-300 cursor-pointer"
        >
          Auto-trigger on target / invalidation cross
        </label>
        {disabledReason && (
          <span className="text-xs text-ink-500 italic" title={disabledReason}>
            ({disabledReason})
          </span>
        )}
      </div>
      {thesis.guard_trigger_id != null && (
        <p className="mt-2 text-xs text-ink-400">
          Linked trigger:{" "}
          <Link
            to={`/triggers/${thesis.guard_trigger_id}`}
            className="text-copper-400 hover:text-copper-300"
            data-testid="guard-trigger-link"
          >
            #{thesis.guard_trigger_id}
          </Link>
        </p>
      )}
    </section>
  );
}

function LinkedPositionsSection({ thesisId }: { thesisId: number }) {
  const { data: positions, isLoading } = usePortfolioPositions({ thesis: thesisId });
  const all = positions ?? [];

  return (
    <section className="mb-8 pb-6 border-b border-rule" data-testid="linked-positions-section">
      <div className="flex items-center gap-3 mb-3">
        <h2 className="ledger-eyebrow">Positions</h2>
        <span className="flex-1 h-px bg-rule" />
        <Link
          to="/portfolio"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors"
        >
          The Book →
        </Link>
      </div>

      {isLoading ? (
        <SkeletonRows rows={2} />
      ) : all.length === 0 ? (
        <EmptyState
          title="No linked positions"
          body="Add a position from the Portfolio page and link it to this thesis."
        />
      ) : (
        <ul className="space-y-1.5">
          {all.map((p) => {
            const pnl = p.unrealized?.unrealized_pnl ?? null;
            const realized = p.realized_pnl ? Number(p.realized_pnl) : null;
            const displayPnl = p.status === "open" ? pnl : realized;
            const pnlColor =
              displayPnl == null
                ? "text-ink-600"
                : displayPnl > 0
                  ? "text-gain-400"
                  : displayPnl < 0
                    ? "text-loss-400"
                    : "text-ink-400";
            return (
              <li
                key={p.id}
                data-testid={`thesis-position-${p.id}`}
                className="flex items-center gap-3 px-3 py-2 rounded border border-rule hover:border-rule-soft hover:bg-copper-500/[0.02] transition-colors"
              >
                <span className="font-mono text-[13px] text-ink-100 font-medium">
                  {p.ticker}
                </span>
                <span
                  className={`font-mono text-[9px] uppercase tracking-loose2 border px-1 py-0.5 rounded-ledger ${
                    p.direction === "long"
                      ? "text-gain-400 border-gain-400/30"
                      : "text-loss-400 border-loss-400/30"
                  }`}
                >
                  {p.direction}
                </span>
                <span className="font-mono text-[12px] text-ink-400">
                  {Number(p.quantity).toLocaleString()} @{" "}
                  {Number(p.avg_cost).toFixed(2)}
                </span>
                <span className="flex-1" />
                {displayPnl != null && (
                  <span
                    data-testid={`thesis-pnl-${p.id}`}
                    className={`font-mono text-[12px] tabular-nums ${pnlColor}`}
                  >
                    {displayPnl >= 0 ? "+" : ""}
                    {displayPnl.toFixed(2)}
                  </span>
                )}
                <Link
                  to="/portfolio"
                  className="font-mono text-[11px] text-ink-500 hover:text-copper-300 transition-colors"
                >
                  →
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

export default function ThesisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tid = id ? parseInt(id, 10) : null;
  const { data: thesis, isLoading } = useThesis(tid);

  if (isLoading) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <SkeletonRows rows={6} />
      </div>
    );
  }

  if (!thesis) {
    return (
      <div className="max-w-3xl mx-auto p-6">
        <EmptyState title="Thesis not found" body="This thesis does not exist or has been deleted." />
      </div>
    );
  }

  return (
    <main className="max-w-3xl mx-auto p-6 ledger-fade-in">
      <ThesisMasthead thesis={thesis} />
      <TrackRecordHint
        ticker={thesis.ticker}
        direction={thesis.direction}
        conviction={thesis.conviction}
      />
      <ThesisFields thesis={thesis} />
      <SourceLinks thesis={thesis} />
      <PriceGuardToggle thesis={thesis} />
      <LinkedPositionsSection thesisId={thesis.id} />
      {thesis.status === "open" && <CloseThesisForm thesisId={thesis.id} />}
      <PostMortemsSection thesisId={thesis.id} postmortems={thesis.postmortems} />
    </main>
  );
}
