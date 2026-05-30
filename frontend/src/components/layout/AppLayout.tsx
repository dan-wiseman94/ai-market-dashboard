import { useCallback, useMemo, useRef, useState } from "react";
import { Outlet, useMatches, useNavigate, type UIMatch } from "react-router-dom";
import TopNav from "./TopNav";
import SideNav from "./SideNav";
import {
  useKeyboardShortcuts,
  useCommandPaletteTrigger,
} from "@/hooks/useKeyboardShortcuts";
import ShortcutHelpDialog from "./ShortcutHelpDialog";
import Breadcrumbs from "./Breadcrumbs";
import { ToastProvider } from "@/hooks/useToast";
import { Toasts } from "@/components/Toasts";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { CommandPalette, type Command } from "@/components/CommandPalette";
import { useTheme } from "@/hooks/useTheme";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useRunBriefing } from "@/hooks/useBriefing";
import { useRecall } from "@/hooks/useRecall";

type CrumbFn = (m: UIMatch) => string;
type Handle = { crumb?: string | CrumbFn };

function resolveCrumb(match: UIMatch): string | null {
  const h = match.handle as Handle | undefined;
  if (!h?.crumb) return null;
  if (typeof h.crumb === "string") return h.crumb;
  return h.crumb(match);
}

function useDefaultCommands(onShowHelp: () => void): Command[] {
  const nav = useNavigate();
  const { cycle } = useTheme();
  const runBriefing = useRunBriefing();
  return useMemo(
    () => [
      { id: "go-dashboard", label: "Go to Dashboard", keywords: "home", run: () => nav("/") },
      { id: "go-threads", label: "Go to Threads", keywords: "chats ai", run: () => nav("/threads") },
      { id: "go-snapshot", label: "New snapshot", keywords: "capture", run: () => nav("/snapshot") },
      { id: "go-triggers", label: "Go to Triggers", keywords: "alerts rules", run: () => nav("/triggers") },
      { id: "go-costs", label: "Go to Costs", keywords: "spend usage", run: () => nav("/costs") },
      { id: "go-schedules", label: "Go to Schedules", keywords: "observer cron", run: () => nav("/schedules") },
      { id: "go-backups", label: "Go to Backups", keywords: "backup restore", run: () => nav("/settings/backups") },
      { id: "go-profiles", label: "Go to Profiles", keywords: "style", run: () => nav("/profiles") },
      { id: "go-settings", label: "Open Settings", keywords: "providers keys", run: () => nav("/settings") },
      { id: "go-exports", label: "Go to Exports", keywords: "download zip", run: () => nav("/settings/export") },
      { id: "go-analytics", label: "Go to Analytics", keywords: "leaderboard cpi heatmap",
        run: () => nav("/analytics") },
      { id: "go-scorecard", label: "Go to Scorecard", keywords: "calibration brier conviction hit rate trust",
        run: () => nav("/scorecard") },
      { id: "go-theses", label: "Go to Theses", keywords: "thesis decision call",
        run: () => nav("/theses") },
      { id: "go-events", label: "Go to Events", keywords: "earnings calendar fomc cpi macro", run: () => nav("/events") },
      { id: "go-briefing", label: "Go to Briefing", keywords: "morning digest summary daily", run: () => nav("/briefing") },
      { id: "go-snapshots", label: "Go to Snapshots", keywords: "history browse compare", run: () => nav("/snapshots") },
      { id: "go-recall", label: "Go to Recall", keywords: "search semantic memory observations notes",
        run: () => nav("/recall") },
      { id: "toggle-theme", label: "Toggle theme", keywords: "light dark system appearance mode",
        run: cycle },
      // --- Action verbs ---
      {
        id: "action-run-briefing",
        label: "Run morning briefing now",
        keywords: "briefing digest run trigger now",
        run: () => { runBriefing.mutate(undefined); },
      },
      {
        id: "action-show-shortcuts",
        label: "Show keyboard shortcuts",
        keywords: "help shortcuts keys hotkeys",
        run: onShowHelp,
      },
    ],
    [nav, cycle, runBriefing, onShowHelp],
  );
}

/**
 * Debounces a palette query and returns Recall search hits as Command objects.
 * Only fires when query length >= 2. Results are appended as "Recall" section items.
 */
function useRecallCommands(query: string): Command[] {
  const nav = useNavigate();
  const { data } = useRecall(query.trim().length >= 2 ? query : "", { k: 5 });
  return useMemo(() => {
    if (!data?.results?.length) return [];
    return data.results.map((hit) => ({
      id: `recall:${hit.kind}:${hit.object_id}`,
      label: hit.snippet.length > 80 ? hit.snippet.slice(0, 77) + "…" : hit.snippet,
      section: "Recall",
      keywords: hit.tickers?.join(" ") ?? "",
      run: () => nav(hit.link),
    }));
  }, [data, nav]);
}

export default function AppLayout() {
  const [helpOpen, setHelpOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const handleHelp = useCallback(() => setHelpOpen(true), []);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  useKeyboardShortcuts(handleHelp);
  useCommandPaletteTrigger(openPalette);

  // Debounce the palette query for the recall search (200 ms).
  // When the palette closes we reset the query in the render-phase guard below
  // so that stale recall results don't appear when the palette reopens.
  const [paletteQuery, setPaletteQuery] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleQueryChange = useCallback((q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => { setPaletteQuery(q); }, 200);
  }, []);
  // Render-phase reset: clear the debounced query when the palette closes.
  // Uses the "adjust state when a prop changes" pattern (no effect, no ref reads
  // during render) so react-hooks/set-state-in-effect is not triggered.
  const [prevPaletteOpen, setPrevPaletteOpen] = useState(paletteOpen);
  if (paletteOpen !== prevPaletteOpen) {
    setPrevPaletteOpen(paletteOpen);
    if (!paletteOpen) {
      setPaletteQuery("");
    }
  }

  const commands = useDefaultCommands(handleHelp);
  const recallCommands = useRecallCommands(paletteQuery);

  // Derive the leaf (deepest) crumb from the router matches and set it as the
  // browser tab title. Reuses the same resolveCrumb logic as Breadcrumbs so
  // every route that has a handle.crumb automatically gets a title.
  const matches = useMatches();
  const leafCrumb = useMemo(() => {
    const crumbs = matches
      .map((m) => resolveCrumb(m))
      .filter((c): c is string => c !== null);
    return crumbs.at(-1) ?? undefined;
  }, [matches]);
  useDocumentTitle(leafCrumb);

  return (
    <ToastProvider>
      <div className="relative min-h-screen text-ink-100 flex flex-col">
        <div
          aria-hidden
          className="pointer-events-none fixed inset-0 -z-10"
          style={{
            background:
              "radial-gradient(ellipse 900px 500px at 10% -10%, rgba(200,150,88,0.09), transparent 70%), radial-gradient(ellipse 700px 400px at 95% 110%, rgba(70,90,120,0.16), transparent 65%)",
          }}
        />
        <TopNav />
        <div className="flex flex-1 min-h-0">
          <SideNav />
          <main className="flex-1 min-w-0 relative">
            <Breadcrumbs />
            <ErrorBoundary>
              <Outlet />
            </ErrorBoundary>
          </main>
        </div>
        <ShortcutHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
        <CommandPalette
          open={paletteOpen}
          onClose={() => setPaletteOpen(false)}
          commands={commands}
          extraCommands={recallCommands}
          onQueryChange={handleQueryChange}
        />
        <Toasts />
      </div>
    </ToastProvider>
  );
}
