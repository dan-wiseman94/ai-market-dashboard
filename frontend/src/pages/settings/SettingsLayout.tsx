import { NavLink, Outlet } from "react-router-dom";

const SECTIONS: Array<[string, string, string]> = [
  ["/settings", "AI Providers", "AI"],
  ["/settings/connections", "Connections", "CX"],
  ["/settings/backups", "Backups", "BK"],
  ["/settings/export", "Export", "EX"],
];

export default function SettingsLayout() {
  return (
    <main className="px-8 py-8 max-w-[1100px] mx-auto ledger-fade-in">
      <header className="mb-8 pb-6 border-b border-rule">
        <div className="flex items-center gap-4 mb-3">
          <span className="ledger-eyebrow">Ledger · Settings</span>
          <span className="flex-1 h-px bg-rule-soft" />
        </div>
        <h1 className="ledger-display" style={{ fontSize: "clamp(1.5rem, 2.6vw, 2.25rem)" }}>
          Configure your <em className="italic text-copper-300">terminal</em>.
        </h1>
        <p className="mt-2 text-ink-300 text-[14px] max-w-xl">
          Providers, connections, and housekeeping — all in one place.
        </p>
      </header>

      <div className="grid grid-cols-[180px_1fr] gap-8 items-start max-md:grid-cols-1">
        <nav aria-label="Settings sections" className="md:sticky md:top-6">
          <ul className="space-y-0.5">
            {SECTIONS.map(([to, label, mono]) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={to === "/settings"}
                  className={({ isActive }) =>
                    [
                      "relative flex items-center gap-3 rounded-sm px-2.5 py-1.5 transition-colors duration-150 ease-ledger",
                      isActive ? "text-copper-200" : "text-ink-300 hover:text-ink-100",
                    ].join(" ")
                  }
                >
                  {({ isActive }) => (
                    <>
                      {isActive && <span aria-hidden className="absolute left-0 top-1 bottom-1 w-[2px] bg-copper-500" />}
                      <span className={`font-mono text-[10px] ${isActive ? "text-copper-400" : "text-ink-500"}`} aria-hidden>
                        {mono}
                      </span>
                      <span className="text-[13px] font-medium tracking-wide">{label}</span>
                    </>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </main>
  );
}
