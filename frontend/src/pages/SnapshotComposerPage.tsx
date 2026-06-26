import { useMemo, useState } from "react";
import { useNavigate, type NavigateFunction } from "react-router-dom";
import { ApiError } from "@/api/client";
import { waitForSnapshotReady } from "@/api/snapshots";
import SnapshotSectionPicker from "@/components/SnapshotSectionPicker";
import { SnapshotCaptureProgress } from "@/components/SnapshotCaptureProgress";
import TickerChipsInput from "@/components/TickerChipsInput";
import { useProfiles } from "@/hooks/useProfiles";
import { useAgentPresets } from "@/hooks/useAgentPresets";
import { useCreateSnapshot } from "@/hooks/useCreateSnapshot";
import { useCreateConsultThread } from "@/hooks/useCreateConsultThread";
import { useWatchlists } from "@/hooks/useWatchlists";
import { useMarketStatus } from "@/hooks/useMarketStatus";
import { useSnapshotProgress } from "@/hooks/useSnapshotProgress";

function readStagedIds(): number[] {
  try {
    return JSON.parse(localStorage.getItem("staged_image_ids") || "[]");
  } catch {
    return [];
  }
}

// Effective ticker set = the selected watchlist's symbols plus any ad-hoc
// tickers the user typed, de-duplicated with watchlist symbols kept first.
function watchlistTickersOf(
  watchlists: ReturnType<typeof useWatchlists>["data"],
  watchlistId: number | null,
): string[] {
  return watchlists?.find((w) => w.id === watchlistId)?.symbols.map((s) => s.ticker) ?? [];
}

function closedMarketsOf(marketStatus: ReturnType<typeof useMarketStatus>["data"]): string[] {
  if (!marketStatus) return [];
  return Object.entries(marketStatus.markets)
    .filter(([, s]) => !s.is_open)
    .map(([k]) => k);
}

function threadTitle(title: string, objective: string): string {
  // Explicit title wins; otherwise fall back to the objective / a timestamp.
  return title.trim() || objective.slice(0, 80) || `Consult ${new Date().toLocaleString()}`;
}

interface CaptureFields {
  profileId: number | null;
  objective: string;
  notes: string;
  includes: string[];
  manualPositions: string;
  candidatePositions: string;
  tickers: string[];
  stagedIds: number[];
  title: string;
}

interface RunCaptureDeps {
  fields: CaptureFields;
  createSnap: ReturnType<typeof useCreateSnapshot>;
  createThread: ReturnType<typeof useCreateConsultThread>;
  navigate: NavigateFunction;
  setCapturingId: (id: number | null) => void;
  setStagedIds: (ids: number[]) => void;
}

async function runCapture(deps: RunCaptureDeps): Promise<void> {
  const { fields, createSnap, createThread, navigate, setCapturingId, setStagedIds } = deps;
  const { profileId } = fields;
  if (!profileId) return;
  const created = await createSnap.mutateAsync({
    profile_id: profileId,
    objective: fields.objective,
    notes: fields.notes,
    includes: fields.includes,
    manual_positions: fields.manualPositions,
    candidate_positions: fields.candidatePositions,
    watchlist_tickers: fields.tickers,
    ohlc_ticker: fields.tickers[0],
    ohlc_timeframe: "1m",
    ohlc_bars: 60,
    image_ids: fields.stagedIds,
  });
  // Subscribe to the WS channel for live per-section progress. The HTTP
  // poll below remains the terminal source of truth — WS is progress-only.
  setCapturingId(created.id);
  // Capture runs asynchronously in a Celery worker, so the snapshot comes
  // back as "pending". Wait for it to finish before pinning it to a thread —
  // the thread-create endpoint 400s on a non-ready snapshot.
  const snap = created.status === "ready" ? created : await waitForSnapshotReady(created.id);
  const thread = await createThread.mutateAsync({
    profile_id: profileId,
    pinned_snapshot_id: snap.id,
    title: threadTitle(fields.title, fields.objective),
    // "Capture + ask": stream the AI's reply to the snapshot immediately so the
    // thread page isn't silent on arrival.
    auto_reply: true,
  });
  localStorage.removeItem("staged_image_ids");
  setStagedIds([]);
  navigate(`/threads/${thread.id}?snapshot=${snap.id}`);
}

function ClosedMarketsBanner({ markets }: { markets: string[] }) {
  if (markets.length === 0) return null;
  return (
    <div role="status" className="rounded border border-copper-500/40 bg-copper-500/10 px-3 py-2 text-sm text-copper-300">
      Market closed ({markets.join(", ")}) — this snapshot will be captured and labeled
      as-of the last session close.
    </div>
  );
}

function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <div role="alert" className="rounded border border-loss-500/40 bg-loss-500/10 px-3 py-2 text-sm text-loss-400">
      {error}
    </div>
  );
}

function ProfileField({
  profileId,
  profiles,
  onChange,
}: {
  profileId: number | null;
  profiles: ReturnType<typeof useProfiles>["data"];
  onChange: (id: number | null) => void;
}) {
  return (
    <div>
      <label className="block text-xs text-ink-500 mb-1">Profile</label>
      <select
        value={profileId ?? ""}
        onChange={(e) => onChange(parseInt(e.target.value, 10) || null)}
        className="w-full px-2 py-1.5 rounded bg-ink-900 border border-rule"
      >
        <option value="" disabled>Select profile…</option>
        {(profiles ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
    </div>
  );
}

function WatchlistField({
  watchlistId,
  watchlists,
  watchlistTickers,
  onChange,
}: {
  watchlistId: number | null;
  watchlists: ReturnType<typeof useWatchlists>["data"];
  watchlistTickers: string[];
  onChange: (id: number | null) => void;
}) {
  return (
    <div>
      <label className="block text-xs text-ink-500 mb-1">
        Watchlist (provides tickers for quotes + OHLC)
      </label>
      <select
        value={watchlistId ?? ""}
        onChange={(e) => onChange(parseInt(e.target.value, 10) || null)}
        className="w-full px-2 py-1.5 rounded bg-ink-900 border border-rule"
      >
        <option value="" disabled>Select watchlist…</option>
        {(watchlists ?? []).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
      </select>
      <div className="text-xs text-ink-500 mt-1">
        {watchlistTickers.join(", ") || "(no symbols)"}
      </div>
    </div>
  );
}

function PresetField({
  presets,
  onSetObjective,
}: {
  presets: ReturnType<typeof useAgentPresets>["data"];
  onSetObjective: (v: string) => void;
}) {
  const activePresets = (presets ?? []).filter((p) => p.active);
  if (activePresets.length === 0) return null;
  return (
    <div>
      <label className="block text-xs text-ink-500 mb-1">Apply a preset</label>
      <select
        defaultValue=""
        onChange={(e) => {
          const preset = activePresets.find((p) => String(p.id) === e.target.value);
          if (preset) {
            onSetObjective(preset.objective_template);
          }
          // Reset to placeholder so the user can re-apply the same preset
          e.target.value = "";
        }}
        className="w-full px-2 py-1.5 rounded bg-ink-900 border border-rule text-ink-300"
        aria-label="Apply a preset"
      >
        <option value="" disabled>Apply a preset…</option>
        {activePresets.map((p) => (
          <option key={p.id} value={p.id}>{p.name}</option>
        ))}
      </select>
    </div>
  );
}

function StagedImages({
  stagedIds,
  onDrop,
}: {
  stagedIds: number[];
  onDrop: (id: number) => void;
}) {
  if (stagedIds.length === 0) return null;
  return (
    <div>
      <label className="block text-xs text-ink-500 mb-1">Staged screenshots</label>
      <div className="flex gap-2 flex-wrap">
        {stagedIds.map((id) => (
          <div key={id} className="relative border border-rule rounded">
            <img src={`/api/snapshots/images/${id}/`} alt={`staged ${id}`}
                 className="h-16 w-auto block" />
            <button
              type="button"
              onClick={() => onDrop(id)}
              aria-label={`drop staged image ${id}`}
              className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-loss-500 text-white text-xs leading-none border border-loss-400 cursor-pointer p-0"
            >×</button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function SnapshotComposerPage() {
  const navigate = useNavigate();
  const { data: profiles } = useProfiles();
  const { data: watchlists } = useWatchlists();
  const { data: presets } = useAgentPresets();
  const createSnap = useCreateSnapshot();
  const createThread = useCreateConsultThread();

  const [profileId, setProfileId] = useState<number | null>(null);
  const [watchlistId, setWatchlistId] = useState<number | null>(null);
  const [customTickers, setCustomTickers] = useState<string[]>([]);
  const [includes, setIncludes] = useState<string[]>(["quotes", "positions", "breadth"]);
  const [objective, setObjective] = useState("");
  const [notes, setNotes] = useState("");
  const [manualPositions, setManualPositions] = useState("");
  const [candidatePositions, setCandidatePositions] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Set to the created snapshot id once the POST returns so we can subscribe
  // to its WS channel for live per-section progress events. Cleared on terminal
  // (navigation away or error). The HTTP poll remains the terminal source of
  // truth — this is progress-only.
  const [capturingId, setCapturingId] = useState<number | null>(null);
  const { sections: captureSections } = useSnapshotProgress(capturingId);
  const [stagedIds, setStagedIds] = useState<number[]>(readStagedIds);

  function dropStaged(id: number) {
    const next = stagedIds.filter((x) => x !== id);
    setStagedIds(next);
    localStorage.setItem("staged_image_ids", JSON.stringify(next));
  }

  // Default selections to the first profile/watchlist once loaded. Render-phase
  // guarded updates (React's "adjust state when data changes") rather than
  // effects, which avoids react-hooks/set-state-in-effect cascading renders.
  if (profileId === null && profiles && profiles.length > 0) {
    setProfileId(profiles[0].id);
    setIncludes(profiles[0].default_includes);
  }
  if (watchlistId === null && watchlists && watchlists.length > 0) {
    setWatchlistId(watchlists[0].id);
  }

  const watchlistTickers = useMemo(
    () => watchlistTickersOf(watchlists, watchlistId),
    [watchlists, watchlistId],
  );

  const tickers = useMemo(
    () => Array.from(new Set([...watchlistTickers, ...customTickers])),
    [watchlistTickers, customTickers],
  );

  const { data: marketStatus } = useMarketStatus(tickers);
  const closedMarkets = closedMarketsOf(marketStatus);

  const onCapture = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profileId) return;
    setError(null);
    setSubmitting(true);
    try {
      await runCapture({
        fields: {
          profileId, objective, notes, includes, manualPositions,
          candidatePositions, tickers, stagedIds, title,
        },
        createSnap,
        createThread,
        navigate,
        setCapturingId,
        setStagedIds,
      });
    } catch (err) {
      setCapturingId(null);
      setError(
        err instanceof ApiError ? err.message : "Failed to capture snapshot — please try again.",
      );
      setSubmitting(false);
    }
  };

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">New snapshot</h1>

      <ClosedMarketsBanner markets={closedMarkets} />

      <ErrorBanner error={error} />

      <form onSubmit={onCapture} className="space-y-4">
        <ProfileField profileId={profileId} profiles={profiles} onChange={setProfileId} />

        <WatchlistField
          watchlistId={watchlistId}
          watchlists={watchlists}
          watchlistTickers={watchlistTickers}
          onChange={setWatchlistId}
        />

        <div>
          <label className="block text-xs text-ink-500 mb-1">Add tickers (optional)</label>
          <TickerChipsInput value={customTickers} onChange={setCustomTickers} />
          <div className="text-xs text-ink-500 mt-1">
            Using: {tickers.join(", ") || "(none — notes/market context only)"}
          </div>
        </div>

        <div>
          <label className="block text-xs text-ink-500 mb-1">Sections</label>
          <SnapshotSectionPicker value={includes} onChange={setIncludes} />
        </div>

        <PresetField presets={presets} onSetIncludes={setIncludes} onSetObjective={setObjective} />

        <div>
          <label className="block text-xs text-ink-500 mb-1">Thread title (optional)</label>
          <input
            type="text" value={title} onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            placeholder="Defaults to the objective if left blank"
            className="w-full px-2 py-1.5 rounded bg-ink-900 border border-rule"
          />
        </div>

        <div>
          <label className="block text-xs text-ink-500 mb-1">Objective</label>
          <textarea
            rows={3} value={objective} onChange={(e) => setObjective(e.target.value)}
            placeholder="What do you want the AI to consider right now?"
            className="w-full px-2 py-1.5 rounded bg-ink-900 border border-rule"
          />
        </div>

        <div>
          <label className="block text-xs text-ink-500 mb-1">Notes (optional)</label>
          <textarea
            rows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
            className="w-full px-2 py-1.5 rounded bg-ink-900 border border-rule"
          />
        </div>

        <div>
          <label className="block text-xs text-ink-500 mb-1">Current positions (optional, free text)</label>
          <textarea
            rows={3} value={manualPositions} onChange={(e) => setManualPositions(e.target.value)}
            placeholder="Holdings you want the AI to manage — e.g. &#10;100 SPY @ 450&#10;2x AAPL 180c exp 6/20"
            className="w-full px-2 py-1.5 rounded bg-ink-900 border border-rule font-mono text-sm"
          />
          <div className="text-xs text-ink-500 mt-1">
            Parsed by the AI — no broker connection needed.
          </div>
        </div>

        <div>
          <label className="block text-xs text-ink-500 mb-1">
            Potential positions to discuss (optional, free text)
          </label>
          <textarea
            rows={3} value={candidatePositions} onChange={(e) => setCandidatePositions(e.target.value)}
            placeholder="Trades you're weighing — the AI evaluates the entry case, e.g. &#10;long NVDA 6mo&#10;short QQQ hedge"
            className="w-full px-2 py-1.5 rounded bg-ink-900 border border-rule font-mono text-sm"
          />
          <div className="text-xs text-ink-500 mt-1">
            Candidates under consideration — not assumed to be held.
          </div>
        </div>

        <StagedImages stagedIds={stagedIds} onDrop={dropStaged} />

        {submitting && captureSections.size > 0 && (
          <div data-testid="capture-progress">
            <SnapshotCaptureProgress sections={captureSections} />
          </div>
        )}

        <button
          data-testid="capture-btn"
          disabled={!profileId || submitting}
          className="px-4 py-2 rounded bg-gain-500 hover:bg-gain-400 disabled:opacity-40"
        >
          {submitting ? "Capturing…" : "Capture + ask"}
        </button>
      </form>
    </main>
  );
}
