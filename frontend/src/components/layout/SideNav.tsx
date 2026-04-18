import { NavLink } from "react-router-dom";
import { useSidebarCollapsed } from "@/hooks/useSidebarCollapsed";

const TRADING: Array<[string, string]> = [
  ["/profiles", "Profiles"],
  ["/watchlists", "Watchlists"],
];
const SYSTEM: Array<[string, string]> = [
  ["/settings", "Settings"],
];

export default function SideNav() {
  const [collapsed, toggle] = useSidebarCollapsed();
  return (
    <aside className={`border-r border-slate-800 ${collapsed ? "w-12" : "w-48"} transition-all shrink-0`}>
      <button
        aria-label="Toggle sidebar"
        onClick={toggle}
        className="w-full p-2 text-xs text-slate-400 hover:text-slate-200"
      >
        {collapsed ? "»" : "«"}
      </button>
      {!collapsed && (
        <div className="p-2 space-y-4 text-sm">
          <Section title="Trading" links={TRADING} />
          <Section title="System" links={SYSTEM} />
        </div>
      )}
    </aside>
  );
}

function Section({ title, links }: { title: string; links: Array<[string, string]> }) {
  return (
    <div>
      <div className="text-xs uppercase text-slate-500 mb-1">{title}</div>
      {links.map(([to, label]) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `block px-2 py-1 rounded ${isActive ? "bg-slate-800 text-emerald-300" : "text-slate-300 hover:bg-slate-800/60"}`
          }
        >
          {label}
        </NavLink>
      ))}
    </div>
  );
}
