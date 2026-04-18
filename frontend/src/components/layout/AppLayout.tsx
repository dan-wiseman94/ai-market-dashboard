import { useCallback, useState } from "react";
import { Outlet } from "react-router-dom";
import TopNav from "./TopNav";
import SideNav from "./SideNav";
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts";
import ShortcutHelpDialog from "./ShortcutHelpDialog";
import Breadcrumbs from "./Breadcrumbs";

export default function AppLayout() {
  const [helpOpen, setHelpOpen] = useState(false);
  const handleHelp = useCallback(() => setHelpOpen(true), []);
  useKeyboardShortcuts(handleHelp);
  return (
    <div className="relative min-h-screen text-ink-100 flex flex-col">
      {/* Decorative ambient wash — copper at top-left, cool at bottom-right */}
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
          <Outlet />
        </main>
      </div>
      <ShortcutHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
