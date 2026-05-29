import { useCallback, useMemo, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
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

function useDefaultCommands(): Command[] {
  const nav = useNavigate();
  const { cycle } = useTheme();
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
    ],
    [nav, cycle],
  );
}

export default function AppLayout() {
  const [helpOpen, setHelpOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const handleHelp = useCallback(() => setHelpOpen(true), []);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  useKeyboardShortcuts(handleHelp);
  useCommandPaletteTrigger(openPalette);
  const commands = useDefaultCommands();

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
        />
        <Toasts />
      </div>
    </ToastProvider>
  );
}
