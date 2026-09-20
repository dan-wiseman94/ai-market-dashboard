import AiAttribution from "@/components/ai/AiAttribution";
import type { WarRoomVerdictContent } from "@/api/observation";

function Line({ label, value }: { label: string; value?: string }) {
  if (!value) return null;
  return (
    <p className="text-sm text-ink-300">
      <span className="text-ink-500">{label}:</span> {value}
    </p>
  );
}

/** The synthesizer's verdict on a War Room debate. */
export default function WarRoomVerdictBody({ verdict }: { verdict: WarRoomVerdictContent }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium text-ink-100">{verdict.verdict}</span>
        {verdict.confidence != null && (
          <span className="ledger-pill" data-tone="copper">
            {Math.round(verdict.confidence * 100)}% conf
          </span>
        )}
        {verdict.ai && <AiAttribution provider={verdict.ai.provider} model={verdict.ai.model} />}
      </div>
      <Line label="Strongest bull" value={verdict.strongest_bull} />
      <Line label="Strongest bear" value={verdict.strongest_bear} />
      <Line label="What would change my mind" value={verdict.what_would_change_my_mind} />
    </div>
  );
}
