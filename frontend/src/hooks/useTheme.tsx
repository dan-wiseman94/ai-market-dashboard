import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

const STORAGE_KEY = "ai-dashboard.theme";
const MEDIA = "(prefers-color-scheme: dark)";

interface ThemeContextValue {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (p: ThemePreference) => void;
  cycle: () => void;
}

function systemPrefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return true;
  return window.matchMedia(MEDIA).matches;
}

function readPreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" || v === "system" ? v : "system";
}

function applyTheme(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.classList.toggle("light", resolved === "light");
  root.style.colorScheme = resolved;
  document
    .querySelector('meta[name="color-scheme"]')
    ?.setAttribute("content", resolved);
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", resolved === "dark" ? "#0b0d12" : "#f5f2ea");
}

// Non-throwing default so components using useTheme() render without a provider
// (e.g. unit tests). The provider upgrades this to the live, reactive value.
const ThemeContext = createContext<ThemeContextValue>({
  preference: "system",
  resolved: "dark",
  setPreference: () => {},
  cycle: () => {},
});

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(readPreference);
  const [systemDark, setSystemDark] = useState<boolean>(systemPrefersDark);

  // resolved is DERIVED during render — no setState-in-effect.
  const resolved: ResolvedTheme =
    preference === "system" ? (systemDark ? "dark" : "light") : preference;

  // Apply the resolved theme to the DOM (side effect only — no setState).
  useEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  // Persist the preference (side effect only — no setState).
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      /* storage unavailable — ignore */
    }
  }, [preference]);

  // Follow the OS while in "system". The listener updates systemDark from an
  // event handler (allowed), never synchronously inside the effect body.
  useEffect(() => {
    if (preference !== "system" || typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(MEDIA);
    const onChange = () => setSystemDark(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [preference]);

  const cycle = useCallback(() => {
    setPreference((p) => (p === "light" ? "dark" : p === "dark" ? "system" : "light"));
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({ preference, resolved, setPreference, cycle }),
    [preference, resolved, cycle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
