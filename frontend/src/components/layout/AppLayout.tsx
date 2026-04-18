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
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      <TopNav />
      <div className="flex flex-1 min-h-0">
        <SideNav />
        <main className="flex-1 min-w-0">
          <Breadcrumbs />
          <Outlet />
        </main>
      </div>
      <ShortcutHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </div>
  );
}
