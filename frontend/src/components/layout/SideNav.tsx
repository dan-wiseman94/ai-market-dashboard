import { NavLink } from "react-router-dom";
import { useSidebarCollapsed } from "@/hooks/useSidebarCollapsed";

const TRADING: Array<[string, string, string]> = [
  ["/profiles", "Profiles", "PR"],
  ["/watchlists", "Watchlists", "WL"],
];
const SYSTEM: Array<[string, string, string]> = [
  ["/settings", "Settings", "ST"],
];

export default function SideNav() {
  const [collapsed, toggle] = useSidebarCollapsed();
  return (
    <aside
      className={[
        "relative border-r border-rule shrink-0",
        collapsed ? "w-14" : "w-56",
        "transition-[width] duration-300 ease-ledger",
      ].join(" ")}
    >
      {/* Vertical copper hairline flush to the main content edge */}
      <div
        aria-hidden
        className="absolute top-0 right-0 bottom-0 w-px"
        style={{
          background:
            "linear-gradient(180deg, transparent 0%, color-mix(in srgb, var(--copper-500) 28%, transparent) 12%, var(--rule) 50%, transparent 100%)",
        }}
      />

      <button
        aria-label="Toggle sidebar"
        onClick={toggle}
        className={[
          "group flex items-center gap-2 w-full px-3 py-3 font-mono text-[10px] uppercase tracking-loose2",
          "text-ink-400 hover:text-copper-300 transition-colors",
        ].join(" ")}
      >
        <span
          className="inline-block h-px w-4 bg-rule group-hover:bg-copper-400 transition-colors"
          aria-hidden
        />
        {!collapsed && <span>Collapse</span>}
      </button>

      <div className={[collapsed ? "px-2" : "px-3", "space-y-6"].join(" ")}>
        <Section title="Trading" links={TRADING} collapsed={collapsed} />
        <Section title="System"  links={SYSTEM}  collapsed={collapsed} />
      </div>
    </aside>
  );
}

function Section({
  title, links, collapsed,
}: {
  title: string;
  links: Array<[string, string, string]>;
  collapsed: boolean;
}) {
  return (
    <div>
      {!collapsed && (
        <div className="ledger-eyebrow mb-2 px-2 flex items-center gap-2">
          <span>{title}</span>
          <span className="flex-1 h-px bg-rule" />
        </div>
      )}
      <ul className="space-y-0.5">
        {links.map(([to, label, mono]) => (
          <li key={to}>
            <NavLink
              to={to}
              className={({ isActive }) =>
                [
                  "relative flex items-center gap-3 rounded-sm transition-colors duration-150 ease-ledger",
                  collapsed ? "justify-center px-0 py-2" : "px-2.5 py-1.5",
                  isActive
                    ? "text-copper-200"
                    : "text-ink-300 hover:text-ink-100",
                ].join(" ")
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && (
                    <span
                      aria-hidden
                      className="absolute left-0 top-1 bottom-1 w-[2px] bg-copper-500"
                    />
                  )}
                  <span
                    className={[
                      "font-mono text-[10px]",
                      isActive ? "text-copper-400" : "text-ink-500",
                    ].join(" ")}
                    aria-hidden
                  >
                    {mono}
                  </span>
                  {!collapsed && (
                    <span className="text-[13px] font-medium tracking-wide">{label}</span>
                  )}
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}
