import { useRef } from "react";
import { VerdictBadge } from "@/components/thesis/ThesisBadges";
import { SaveCardButton } from "@/components/SaveCardButton";
import type { PostMortem, PostMortemReport } from "@/api/thesis";

function formatReturn(pct: number | null): string {
  if (pct === null) return "—";
  const sign = pct >= 0 ? "+" : "−";
  return `${sign}${Math.abs(pct).toFixed(1)}%`;
}

function isPopulatedReport(
  report: PostMortem["report"],
): report is PostMortemReport {
  return typeof (report as PostMortemReport).summary === "string";
}

function ForwardReturn({ pm }: { pm: PostMortem }) {
  const testid = `pm-return-${pm.horizon_days}`;
  if (pm.forward_return_pct === null) {
    return (
      <span className="font-mono text-[13px] text-ink-500" data-testid={testid}>
        —
      </span>
    );
  }
  return (
    <span
      className={`font-mono text-[13px] font-medium ${
        pm.forward_return_pct >= 0 ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300"
      }`}
      data-testid={testid}
    >
      {formatReturn(pm.forward_return_pct)}
    </span>
  );
}

function ReportList({
  title,
  items,
  itemClassName,
}: {
  title: string;
  items: string[];
  itemClassName: string;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="ledger-eyebrow mb-1">{title}</div>
      <ul className="list-disc list-inside space-y-0.5">
        {items.map((item, i) => (
          <li key={i} className={itemClassName}>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function PostMortemBody({ pm }: { pm: PostMortem }) {
  if (pm.status === "scheduled") {
    return (
      <p className="text-ink-400 text-[13px]">
        Scheduled for{" "}
        {new Date(pm.due_at).toLocaleDateString(undefined, {
          month: "short",
          day: "numeric",
          year: "numeric",
        })}
      </p>
    );
  }

  const report = isPopulatedReport(pm.report) ? pm.report : null;
  if (report) {
    return (
      <div className="space-y-3">
        <p className="text-ink-100 text-[13px] leading-relaxed">
          {report.summary}
        </p>
        <ReportList title="Lessons" items={report.lessons} itemClassName="text-ink-300 text-[12px]" />
        <ReportList title="What worked" items={report.what_worked} itemClassName="text-emerald-700 dark:text-emerald-400 text-[12px]" />
        <ReportList title="What missed" items={report.what_missed} itemClassName="text-rose-700 dark:text-rose-400 text-[12px]" />
      </div>
    );
  }

  if (pm.status === "running") {
    return <p className="text-ink-500 text-[13px] italic">Analysis in progress…</p>;
  }
  if (pm.status === "failed") {
    return <p className="text-ink-500 text-[13px] italic">Analysis failed.</p>;
  }
  return null;
}

export function PostMortemCard({ pm }: { pm: PostMortem }) {
  const isScheduled = pm.status === "scheduled";
  const cardRef = useRef<HTMLDivElement>(null);
  const filename = `postmortem-${pm.horizon_days}d.png`;

  return (
    <div
      ref={cardRef}
      className="ledger-surface px-5 py-4 rounded"
      data-testid={`pm-card-${pm.horizon_days}`}
    >
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <span className="font-mono text-[13px] text-copper-400 font-medium">
          {pm.horizon_days}-day
        </span>
        <span className="font-mono text-[11px] text-ink-400 uppercase tracking-wide">
          {pm.status}
        </span>
        {!isScheduled && <VerdictBadge verdict={pm.verdict} />}
        {!isScheduled && <ForwardReturn pm={pm} />}
        <span className="flex-1" />
        <SaveCardButton targetRef={cardRef} filename={filename} />
      </div>

      <PostMortemBody pm={pm} />
    </div>
  );
}
