import AiAttribution from "@/components/ai/AiAttribution";
import type { PostMortemReportContent } from "@/api/observation";

function ReportList({
  title, items, itemClassName,
}: {
  title: string;
  items: string[];
  itemClassName: string;
}) {
  if (items.length === 0) return null;
  return (
    <section>
      <div className="mb-1 font-mono text-[10px] uppercase tracking-wider text-copper-400">
        {title}
      </div>
      <ul className="list-disc pl-5">
        {items.map((t, i) => <li key={i} className={itemClassName}>{t}</li>)}
      </ul>
    </section>
  );
}

/** The post-mortem narrative as posted into a thesis review thread. */
export default function PostMortemReportBody({ report }: { report: PostMortemReportContent }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="ledger-pill" data-tone={report.would_repeat ? "gain" : "loss"}>
          {report.would_repeat ? "would repeat" : "would not repeat"}
        </span>
        {report.ai && <AiAttribution provider={report.ai.provider} model={report.ai.model} />}
      </div>
      <p className="text-sm text-ink-300">{report.summary}</p>
      <ReportList
        title="What worked"
        items={report.what_worked ?? []}
        itemClassName="text-[12px] text-gain-400"
      />
      <ReportList
        title="What missed"
        items={report.what_missed ?? []}
        itemClassName="text-[12px] text-loss-400"
      />
      <ReportList
        title="Lessons"
        items={report.lessons ?? []}
        itemClassName="text-[12px] text-ink-300"
      />
    </div>
  );
}
