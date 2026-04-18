import { NavLink } from "react-router-dom";
import NotificationBell from "@/components/NotificationBell";
import ConnectionStatusDot from "./ConnectionStatusDot";

const LINKS: Array<[string, string, string]> = [
  ["/", "Dashboard", "g d"],
  ["/snapshot", "Snapshot", "g s"],
  ["/threads", "Threads", "g h"],
  ["/triggers", "Triggers", "g t"],
  ["/schedules", "Schedules", "g o"],
  ["/costs", "Costs", "g c"],
];

function Monogram() {
  return (
    <NavLink to="/" className="flex items-center gap-2.5 group" aria-label="Ledger home">
      <span
        aria-hidden
        className="relative inline-flex h-7 w-7 items-center justify-center"
      >
        <svg viewBox="0 0 28 28" className="h-7 w-7" fill="none">
          <rect
            x="2" y="2" width="24" height="24"
            transform="rotate(45 14 14)"
            stroke="var(--copper-500)" strokeWidth="1.25"
          />
          <rect
            x="8" y="8" width="12" height="12"
            transform="rotate(45 14 14)"
            fill="var(--copper-500)" fillOpacity="0.1"
            stroke="var(--copper-400)" strokeWidth="0.75"
          />
          <line x1="4" y1="14" x2="24" y2="14"
            stroke="var(--copper-300)" strokeWidth="0.6"
            strokeDasharray="1 2" />
        </svg>
        <span className="absolute inset-0 rounded-full bg-copper-500/0 group-hover:bg-copper-500/20 blur-md transition-all duration-300" />
      </span>
      <span className="flex flex-col leading-none">
        <span
          className="font-display text-[17px] font-medium text-ink-50 tracking-tight2"
          style={{ fontVariationSettings: '"opsz" 144, "SOFT" 80' }}
        >
          Ledger
        </span>
        <span className="font-mono text-[9px] uppercase tracking-loose2 text-copper-400 mt-0.5">
          AI · Dashboard
        </span>
      </span>
    </NavLink>
  );
}

export default function TopNav() {
  return (
    <nav
      className="sticky top-0 z-40 border-b border-rule backdrop-blur-md"
      style={{ background: "color-mix(in srgb, var(--ink-950) 85%, transparent)" }}
    >
      <div className="flex items-center gap-6 px-5 h-14">
        <Monogram />

        <div className="h-6 w-px bg-rule" aria-hidden />

        <div className="flex items-center gap-0.5 text-[13px]">
          {LINKS.map(([to, label, shortcut]) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              title={`Shortcut: ${shortcut}`}
              className={({ isActive }) =>
                [
                  "group relative px-3 py-1.5 font-medium tracking-wide transition-colors duration-150 ease-ledger",
                  isActive
                    ? "text-copper-200"
                    : "text-ink-300 hover:text-ink-100",
                ].join(" ")
              }
            >
              {({ isActive }) => (
                <>
                  <span>{label}</span>
                  <span
                    aria-hidden
                    className={[
                      "absolute left-3 right-3 -bottom-[1px] h-px transition-all duration-300 ease-ledger",
                      isActive
                        ? "bg-copper-400 opacity-100"
                        : "bg-copper-400 opacity-0 group-hover:opacity-60",
                    ].join(" ")}
                  />
                </>
              )}
            </NavLink>
          ))}
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-4 text-[12px] text-ink-400 font-mono">
          <span className="hidden md:inline-flex items-center gap-1.5">
            <ConnectionStatusDot />
          </span>
          <NotificationBell />
        </div>
      </div>
    </nav>
  );
}
