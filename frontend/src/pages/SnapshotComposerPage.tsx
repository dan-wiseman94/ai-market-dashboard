import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import SnapshotSectionPicker from "@/components/SnapshotSectionPicker";
import { useProfiles } from "@/hooks/useProfiles";
import { useCreateSnapshot } from "@/hooks/useCreateSnapshot";
import { useCreateConsultThread } from "@/hooks/useCreateConsultThread";
import { useWatchlists } from "@/hooks/useWatchlists";

export default function SnapshotComposerPage() {
  const navigate = useNavigate();
  const { data: profiles } = useProfiles();
  const { data: watchlists } = useWatchlists();
  const createSnap = useCreateSnapshot();
  const createThread = useCreateConsultThread();

  const [profileId, setProfileId] = useState<number | null>(null);
  const [watchlistId, setWatchlistId] = useState<number | null>(null);
  const [includes, setIncludes] = useState<string[]>(["quotes", "positions", "breadth"]);
  const [objective, setObjective] = useState("");
  const [notes, setNotes] = useState("");
  const [stagedIds, setStagedIds] = useState<number[]>(() => {
    try { return JSON.parse(localStorage.getItem("staged_image_ids") || "[]"); }
    catch { return []; }
  });

  function dropStaged(id: number) {
    const next = stagedIds.filter((x) => x !== id);
    setStagedIds(next);
    localStorage.setItem("staged_image_ids", JSON.stringify(next));
  }

  useEffect(() => {
    if (profileId === null && profiles && profiles.length > 0) {
      setProfileId(profiles[0].id);
      setIncludes(profiles[0].default_includes);
    }
  }, [profiles, profileId]);
  useEffect(() => {
    if (watchlistId === null && watchlists && watchlists.length > 0) {
      setWatchlistId(watchlists[0].id);
    }
  }, [watchlists, watchlistId]);

  const tickers = useMemo(
    () => watchlists?.find((w) => w.id === watchlistId)?.symbols.map((s) => s.ticker) ?? [],
    [watchlists, watchlistId],
  );

  const onCapture = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profileId) return;
    const snap = await createSnap.mutateAsync({
      profile_id: profileId,
      objective, notes, includes,
      watchlist_tickers: tickers,
      ohlc_ticker: tickers[0],
      ohlc_timeframe: "1m",
      ohlc_bars: 60,
      image_ids: stagedIds,
    });
    const thread = await createThread.mutateAsync({
      profile_id: profileId, pinned_snapshot_id: snap.id,
      title: objective.slice(0, 80) || `Consult ${new Date().toLocaleString()}`,
    });
    localStorage.removeItem("staged_image_ids");
    setStagedIds([]);
    navigate(`/threads/${thread.id}?snapshot=${snap.id}`);
  };

  return (
    <main className="p-6 max-w-3xl mx-auto space-y-4">
      <h1 className="text-2xl font-semibold">New snapshot</h1>

      <form onSubmit={onCapture} className="space-y-4">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Profile</label>
          <select
            value={profileId ?? ""}
            onChange={(e) => setProfileId(parseInt(e.target.value, 10) || null)}
            className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
          >
            <option value="" disabled>Select profile…</option>
            {(profiles ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">
            Watchlist (provides tickers for quotes + OHLC)
          </label>
          <select
            value={watchlistId ?? ""}
            onChange={(e) => setWatchlistId(parseInt(e.target.value, 10) || null)}
            className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
          >
            <option value="" disabled>Select watchlist…</option>
            {(watchlists ?? []).map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          <div className="text-xs text-slate-500 mt-1">{tickers.join(", ") || "(no symbols)"}</div>
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">Sections</label>
          <SnapshotSectionPicker value={includes} onChange={setIncludes} />
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">Objective</label>
          <textarea
            rows={3} value={objective} onChange={(e) => setObjective(e.target.value)}
            placeholder="What do you want the AI to consider right now?"
            className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
          />
        </div>

        <div>
          <label className="block text-xs text-slate-500 mb-1">Notes (optional)</label>
          <textarea
            rows={2} value={notes} onChange={(e) => setNotes(e.target.value)}
            className="w-full px-2 py-1.5 rounded bg-slate-900 border border-slate-700"
          />
        </div>

        {stagedIds.length > 0 && (
          <div>
            <label className="block text-xs text-slate-500 mb-1">Staged screenshots</label>
            <div className="flex gap-2 flex-wrap">
              {stagedIds.map((id) => (
                <div key={id} className="relative border border-slate-700 rounded">
                  <img src={`/api/snapshots/images/${id}/`} alt={`staged ${id}`}
                       className="h-16 w-auto block" />
                  <button
                    type="button"
                    onClick={() => dropStaged(id)}
                    aria-label={`drop staged image ${id}`}
                    className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-900 text-white text-xs leading-none border border-red-800 cursor-pointer p-0"
                  >×</button>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          data-testid="capture-btn"
          disabled={!profileId || createSnap.isPending || createThread.isPending}
          className="px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40"
        >
          {createSnap.isPending ? "Capturing…" : "Capture + ask"}
        </button>
      </form>
    </main>
  );
}
