import { useRef } from "react";
import { Link } from "react-router-dom";
import { STATUS_BADGE, DIRECTION_LABEL } from "@/components/thesis/ThesisBadges";
import { SaveCardButton } from "@/components/SaveCardButton";
import type { Thesis } from "@/api/thesis";

export function ThesisMasthead({ thesis }: { thesis: Thesis }) {
  const { label: statusLabel, className: statusClass } =
    STATUS_BADGE[thesis.status];
  const mastheadRef = useRef<HTMLElement>(null);
  const filename = `thesis-${thesis.ticker}-${thesis.id}.png`;

  return (
    <header ref={mastheadRef} className="mb-8 pb-6 border-b border-rule">
      <div className="flex items-center gap-3 mb-3">
        <span className="ledger-eyebrow">Thesis · #{thesis.id}</span>
        <span className="flex-1 h-px bg-rule-soft" />
        <Link
          to="/theses"
          className="font-mono text-[11px] text-ink-400 hover:text-copper-300 transition-colors uppercase tracking-wider"
        >
          ← Theses
        </Link>
      </div>
      <div className="flex items-start gap-3">
        <h1
          className="ledger-display flex-1"
          style={{ fontSize: "clamp(1.4rem, 2.2vw, 1.8rem)" }}
        >
          {thesis.title}
        </h1>
        <span
          className={`inline-flex items-center px-2.5 py-1 rounded text-[12px] font-mono font-medium shrink-0 mt-1 ${statusClass}`}
        >
          {statusLabel}
        </span>
        <SaveCardButton targetRef={mastheadRef} filename={filename} />
      </div>
      <div className="flex items-center gap-3 mt-2">
        <span className="font-mono text-[13px] text-copper-400 uppercase tracking-wide">
          {thesis.ticker}
        </span>
        <span className="text-ink-500 font-mono text-[11px]">·</span>
        <span className="font-mono text-[13px] text-ink-300">
          {DIRECTION_LABEL[thesis.direction]}
        </span>
        <span className="text-ink-500 font-mono text-[11px]">·</span>
        <span
          className="font-mono text-[13px] text-copper-400"
          title="Conviction"
          aria-label={`Conviction ${thesis.conviction}`}
        >
          {"★".repeat(thesis.conviction)}
          {"☆".repeat(5 - thesis.conviction)}
        </span>
      </div>
    </header>
  );
}
