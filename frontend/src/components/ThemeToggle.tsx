import { useTheme, type ThemePreference } from "@/hooks/useTheme";

const PREF_LABEL: Record<ThemePreference, string> = {
  light: "Light",
  dark: "Dark",
  system: "System",
};

function Glyph({ preference }: { preference: ThemePreference }) {
  if (preference === "light") {
    return (
      <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden>
        <circle cx="8" cy="8" r="3.2" />
        <path strokeLinecap="round" d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M13 3l-1.4 1.4M4.4 11.6L3 13" />
      </svg>
    );
  }
  if (preference === "dark") {
    return (
      <svg viewBox="0 0 16 16" className="h-4 w-4" fill="currentColor" aria-hidden>
        <path d="M6 1.5A6.5 6.5 0 1 0 14.5 10 5 5 0 0 1 6 1.5z" />
      </svg>
    );
  }
  // system — half-filled disc
  return (
    <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden>
      <circle cx="8" cy="8" r="6" />
      <path fill="currentColor" stroke="none" d="M8 2a6 6 0 0 1 0 12z" />
    </svg>
  );
}

export default function ThemeToggle() {
  const { preference, resolved, cycle } = useTheme();
  const label =
    `Theme: ${PREF_LABEL[preference]}` +
    (preference === "system" ? ` (${resolved})` : "");
  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={label}
      title={`${label} — click to change`}
      data-testid="theme-toggle"
      data-preference={preference}
      className="inline-flex items-center justify-center h-7 w-7 rounded-ledger border border-rule text-ink-300 hover:text-copper-200 hover:border-copper-500/45 transition-colors duration-150"
    >
      <Glyph preference={preference} />
    </button>
  );
}
