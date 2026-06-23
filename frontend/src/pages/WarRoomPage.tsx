import { useState } from "react";
import { Link } from "react-router-dom";

import { Skeleton } from "@/components/Skeleton";
import { useConveneWarRoom, useWarRoomRuns } from "@/hooks/useWarroom";

export default function WarRoomPage() {
  const { data: runs = [], isLoading, isError, refetch } = useWarRoomRuns();
  const convene = useConveneWarRoom();
  const [prompt, setPrompt] = useState("");
  const [structure, setStructure] = useState<"judge_panel" | "rebuttal" | "deep">("rebuttal");
  const [voiceMode, setVoiceMode] = useState<"single" | "multi">("single");
  const [grounded, setGrounded] = useState(true);

  const onConvene = async () => {
    if (!prompt.trim()) return;
    await convene.mutateAsync({ free_prompt: prompt, structure, voice_mode: voiceMode, grounding: grounded });
    setPrompt("");
    refetch();
  };

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto ledger-fade-in">
      <h1 className="text-2xl font-semibold">War Room</h1>
      <p className="mt-1 text-sm text-ink-400">Convene a bull/bear/skeptic debate and get a synthesized verdict.</p>

      <div className="mt-4 flex gap-2">
        <input
          className="flex-1 rounded border border-rule px-3 py-2 text-sm"
          placeholder="Question to debate (e.g. Is NVDA a buy into earnings?)"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
        />
        <select
          className="rounded border border-rule px-2 text-sm"
          value={structure}
          onChange={(e) => setStructure(e.target.value as "judge_panel" | "rebuttal" | "deep")}
        >
          <option value="judge_panel">Judge panel</option>
          <option value="rebuttal">Rebuttal</option>
          <option value="deep">Deep</option>
        </select>
        <select
          className="rounded border border-rule px-2 text-sm"
          value={voiceMode}
          onChange={(e) => setVoiceMode(e.target.value as "single" | "multi")}
        >
          <option value="single">Single provider</option>
          <option value="multi">Multi-provider</option>
        </select>
        <label className="flex items-center gap-1 text-sm text-ink-300">
          <input
            type="checkbox"
            checked={grounded}
            onChange={(e) => setGrounded(e.target.checked)}
          />
          Grounded (use tools)
        </label>
        <button
          className="rounded border border-rule px-4 py-1 text-sm text-ink-300 transition-colors hover:text-copper-300 disabled:opacity-50"
          onClick={onConvene}
          disabled={convene.isPending}
        >
          {convene.isPending ? "Debating…" : "Convene"}
        </button>
      </div>

      <h2 className="mt-8 text-lg font-medium">Past debates</h2>
      {isLoading ? (
        <Skeleton where="warroom" />
      ) : isError ? (
        <div className="mt-2 text-sm text-copper-400">
          Couldn&rsquo;t load past debates.{" "}
          <button className="underline hover:text-copper-300" onClick={() => refetch()}>
            Retry
          </button>
        </div>
      ) : (
        <ul className="mt-2 divide-y divide-rule">
          {runs.map((r) => (
            <li key={r.id} className="py-3">
              <div className="font-medium"><Link to={`/warroom/${r.id}`}>{r.subject_label}</Link></div>
              {r.status === "error" ? (
                <div className="text-sm text-copper-400">{r.error}</div>
              ) : r.status !== "done" || !r.verdict ? (
                <div className="text-sm text-ink-500">Debating…</div>
              ) : (
                <div className="text-sm text-ink-400">
                  Verdict: {r.verdict.verdict}
                  {r.confidence != null && (
                    <span className="text-ink-500"> ({(r.confidence * 100).toFixed(0)}% conf)</span>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
