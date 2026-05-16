import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

export function useCommandPaletteTrigger(onOpen: () => void): void {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        onOpen();
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onOpen]);
}

export const SHORTCUTS: Record<string, { path: string; label: string }> = {
  d: { path: "/", label: "Dashboard" },
  s: { path: "/snapshot", label: "Snapshot" },
  t: { path: "/triggers", label: "Triggers" },
  h: { path: "/threads", label: "Threads" },
  c: { path: "/costs", label: "Costs" },
  o: { path: "/schedules", label: "Schedules" },
  a: { path: "/analytics", label: "Analytics" },
};

function isEditable(el: Element | null): boolean {
  if (!el) return false;
  const tag = el.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if ((el as HTMLElement).isContentEditable === true) return true;
  const role = (el as HTMLElement).getAttribute?.("role");
  if (role === "textbox" || role === "combobox" || role === "searchbox") return true;
  return false;
}

export function useKeyboardShortcuts(onHelp: () => void): void {
  const navigate = useNavigate();
  const pending = useRef<number | null>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isEditable(document.activeElement)) return;

      if (e.key === "?") {
        e.preventDefault();
        onHelp();
        return;
      }

      if (pending.current != null) {
        window.clearTimeout(pending.current);
        pending.current = null;
        const target = SHORTCUTS[e.key.toLowerCase()];
        if (target) {
          e.preventDefault();
          navigate(target.path);
        }
        return;
      }

      if (e.key === "g") {
        pending.current = window.setTimeout(() => { pending.current = null; }, 800);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, onHelp]);
}
