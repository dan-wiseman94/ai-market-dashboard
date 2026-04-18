import { NavLink } from "react-router-dom";
import NotificationBell from "@/components/NotificationBell";
import ConnectionStatusDot from "./ConnectionStatusDot";

const LINKS: Array<[string, string]> = [
  ["/", "Dashboard"],
  ["/snapshot", "Snapshot"],
  ["/threads", "Threads"],
  ["/triggers", "Triggers"],
  ["/schedules", "Schedules"],
  ["/costs", "Costs"],
];

export default function TopNav() {
  return (
    <nav className="sticky top-0 z-40 flex items-center gap-4 px-4 h-12 border-b border-slate-800 bg-slate-950/95 backdrop-blur">
      <NavLink to="/" className="font-semibold text-emerald-400">AI·Dash</NavLink>
      <div className="flex gap-1 text-sm">
        {LINKS.map(([to, label]) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            className={({ isActive }) =>
              `px-2 py-1 rounded ${isActive ? "bg-slate-800 text-emerald-300" : "text-slate-300 hover:bg-slate-800/60"}`
            }
          >
            {label}
          </NavLink>
        ))}
      </div>
      <div className="flex-1" />
      <ConnectionStatusDot />
      <NotificationBell />
    </nav>
  );
}
