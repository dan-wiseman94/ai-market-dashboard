# Light Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a toggle-able warm-paper light theme with a Light/Dark/System control that follows the OS on first visit, persists, and applies before first paint.

**Architecture:** The "Ledger" design system is token-driven (`--ink-*`/`--copper-*`/market vars in `:root`, dark by default). Light mode redefines those variables under an `html.light` selector and aliases the legacy `slate`/`neutral` Tailwind scales to the same `--ink-*` vars, so ~all CSS re-themes centrally with almost no component edits. The few surfaces that bypass CSS — JS-configured charts, inline-`style` hex, and dark-tinted chromatic banners — are handled explicitly. The resolved theme is carried as the `dark`/`light` class on `<html>` (reusing the existing `darkMode: "class"`).

**Tech Stack:** React 19, TypeScript, Tailwind CSS v4 (`@config` + JS config), Vite, Vitest + Testing Library, lightweight-charts, recharts, Storybook.

**Spec:** `docs/superpowers/specs/2026-05-27-light-mode-design.md`

---

## Environment

Light mode is a frontend-only change; its tests are jsdom vitest needing no backend. Run them on the host from the worktree's `frontend/` directory (deps already installed there via `pnpm install --frozen-lockfile`). All commands below run from `<worktree>/frontend`:

- **One unit test file:** `pnpm exec vitest run --project unit src/__tests__/<file>`
- **All unit tests:** `pnpm exec vitest run --project unit`
- **Types + lint:** `pnpm exec tsc --noEmit && pnpm run lint`

Every commit message ends with the standard trailer:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```
Use `LEFTHOOK=0 git commit …` if the pre-commit hook errors on container-relative paths.

The branch is `worktree-light-mode` (already created off `origin/main`, with the spec committed). Default theme stays **dark** throughout — light only appears once toggled, so each task keeps the app working.

---

## Task 1: Light tokens + slate/neutral aliasing (CSS + Tailwind config)

**Files:**
- Modify: `frontend/src/styles/globals.css`
- Modify: `frontend/tailwind.config.ts`

- [ ] **Step 1: Add `color-scheme` to `:root` and the `html.light` token block inside `@layer base`.**

In `frontend/src/styles/globals.css`, find the `:root {` line (inside `@layer base`) and add `color-scheme: dark;` as its first declaration. Then, immediately after the closing `}` of the `:root` block (still inside `@layer base`, before the `html, body {` rule), insert:

```css
  /* ───── Light theme — warm paper. Same var NAMES, role-preserving values.
     Backgrounds elevate whiter; text/recesses go darker. ───── */
  html.light {
    color-scheme: light;

    --ink-void: #e7e1d4;  /* recessed inset (inputs, code, kbd) */
    --ink-950:  #f5f2ea;  /* page background */
    --ink-900:  #fefdfa;  /* elevated card */
    --ink-850:  #faf7f0;  /* secondary surface */
    --ink-800:  #eae4d8;  /* chips / pill bg */
    --ink-700:  #d6cfbf;
    --ink-600:  #bfb7a3;
    --ink-500:  #a39a85;
    --ink-400:  #857d6b;  /* muted / placeholder */
    --ink-300:  #5c5648;  /* secondary text */
    --ink-200:  #2e2a22;  /* prose body */
    --ink-100:  #1c1812;  /* body text */
    --ink-50:   #14110b;  /* bright / display headings */

    /* Copper — deepen text-leaning steps for AA on paper; keep rich fills. */
    --copper-200: #6f4a17;
    --copper-300: #855816;
    --copper-400: #a06f2c;
    --copper-500: #b07e3e;

    /* Market — deepen text-facing 300 steps. */
    --gain-300: #1f7a52;
    --loss-300: #b3322f;

    /* Hairlines — bump copper alpha for visibility on paper.
       --rule-soft (ink-100 @ 8%) auto-corrects to a faint dark line. */
    --rule:        color-mix(in srgb, var(--copper-500) 26%, transparent);
    --rule-strong: color-mix(in srgb, var(--copper-500) 40%, transparent);
  }

  /* Paper atmosphere — replace the dark grain + radial washes. */
  html.light body {
    background-color: var(--ink-950);
    background-image:
      radial-gradient(ellipse 60% 40% at 15% 0%, rgba(160, 111, 44, 0.05), transparent 70%),
      radial-gradient(ellipse 50% 35% at 85% 100%, rgba(120, 110, 90, 0.05), transparent 70%);
  }
```

- [ ] **Step 2: Add `html.light` component overrides inside `@layer components`.**

CSS cascade layers matter: `@layer components` comes *after* `@layer base`, so these overrides MUST live in the components layer to beat the original `.ledger-*` rules. Add at the END of the existing `@layer components { … }` block (before its closing `}`):

```css
  /* ───── Light-theme seams (overloaded tokens / dark-baked surfaces) ───── */
  html.light .ledger-cta { color: var(--ink-50); }        /* dark text stays on copper */
  html.light .ledger-eyebrow { color: var(--copper-600); }
  html.light .ledger-surface {
    background: linear-gradient(180deg, rgba(255,255,255,0.55) 0%, rgba(0,0,0,0.02) 100%),
                var(--ink-900);
  }
  html.light .ledger-surface::before { opacity: 0.4; }
```

- [ ] **Step 3: Alias `slate` and `neutral` to the ink vars in `tailwind.config.ts`.**

In `frontend/tailwind.config.ts`, inside `theme.extend.colors`, add two new keys alongside `ink`/`copper`/`gain`/`loss`:

```ts
        slate: {
          50: "var(--ink-50)", 100: "var(--ink-100)", 200: "var(--ink-200)",
          300: "var(--ink-300)", 400: "var(--ink-400)", 500: "var(--ink-500)",
          600: "var(--ink-600)", 700: "var(--ink-700)", 800: "var(--ink-800)",
          900: "var(--ink-900)", 950: "var(--ink-950)",
        },
        neutral: {
          50: "var(--ink-50)", 100: "var(--ink-100)", 200: "var(--ink-200)",
          300: "var(--ink-300)", 400: "var(--ink-400)", 500: "var(--ink-500)",
          600: "var(--ink-600)", 700: "var(--ink-700)", 800: "var(--ink-800)",
          900: "var(--ink-900)", 950: "var(--ink-950)",
        },
```

- [ ] **Step 4: Verify the build compiles and dark mode is visually unchanged.**

Run: `pnpm exec tsc --noEmit`
Expected: PASS (no type errors).
Then load the app (still dark by default) and confirm nothing regressed — the `slate→ink` remap slightly warms previously slate-blue components (analytics cards, command palette) toward graphite; that's the intended consistency gain.

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/styles/globals.css frontend/tailwind.config.ts
git commit -m "feat(frontend): light theme tokens + slate/neutral->ink aliasing"
```

---

## Task 2: No-flash bootstrap script

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Insert the render-blocking bootstrap script in `<head>`.**

In `frontend/index.html`, immediately after the `<meta name="theme-color" … />` line, insert:

```html
    <script>
      // Apply the resolved theme before first paint to avoid a flash.
      (function () {
        try {
          var pref = localStorage.getItem("ai-dashboard.theme") || "system";
          var dark = pref === "dark" ||
            (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
          var root = document.documentElement;
          root.classList.toggle("dark", dark);
          root.classList.toggle("light", !dark);
          root.style.colorScheme = dark ? "dark" : "light";
        } catch (e) { /* leave the static class="dark" fallback */ }
      })();
    </script>
```

Leave `<html lang="en" class="dark">` as-is — it is the safe fallback if the script throws or storage is blocked.

- [ ] **Step 2: Verify.**

Load the app with `localStorage` empty and the OS set to light: the page should render light immediately (no dark flash). Set `localStorage["ai-dashboard.theme"]="dark"` and reload: dark with no flash. Reset to empty after.

- [ ] **Step 3: Commit.**

```bash
git add frontend/index.html
git commit -m "feat(frontend): no-flash theme bootstrap script"
```

---

## Task 3: `useTheme` hook + provider (+ matchMedia test mock)

**Files:**
- Create: `frontend/src/hooks/useTheme.tsx`
- Modify: `frontend/src/__tests__/setup.ts`
- Test: `frontend/src/__tests__/useTheme.test.tsx`

- [ ] **Step 1: Add a default `matchMedia` mock to the test setup (jsdom lacks it).**

In `frontend/src/__tests__/setup.ts`, after the `ResizeObserver` polyfill block, add:

```ts
// jsdom has no matchMedia; default to "no preference". Tests override per-case.
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
```

- [ ] **Step 2: Write the failing test.**

Create `frontend/src/__tests__/useTheme.test.tsx`:

```tsx
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { ThemeProvider, useTheme } from "@/hooks/useTheme";

function mockMatchMedia(dark: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const mql = {
    matches: dark,
    media: "(prefers-color-scheme: dark)",
    onchange: null,
    addEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
    removeEventListener: (_: string, cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
    addListener: (cb: (e: MediaQueryListEvent) => void) => listeners.add(cb),
    removeListener: (cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb),
    dispatchEvent: () => false,
    _emit(next: boolean) {
      this.matches = next;
      listeners.forEach((cb) => cb({ matches: next } as MediaQueryListEvent));
    },
  };
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(mql));
  return mql;
}

const wrapper = ({ children }: { children: ReactNode }) => <ThemeProvider>{children}</ThemeProvider>;

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "dark";
});
afterEach(() => vi.unstubAllGlobals());

describe("useTheme", () => {
  it("defaults to system and resolves dark from the OS", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.preference).toBe("system");
    expect(result.current.resolved).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("resolves system -> light when the OS prefers light", () => {
    mockMatchMedia(false);
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.resolved).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("persists an explicit preference and applies the class", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => result.current.setPreference("light"));
    expect(result.current.resolved).toBe("light");
    expect(localStorage.getItem("ai-dashboard.theme")).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });

  it("ignores OS changes when an explicit preference is set", () => {
    const mql = mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => result.current.setPreference("light"));
    act(() => mql._emit(true));
    expect(result.current.resolved).toBe("light");
  });

  it("follows OS changes while in system mode", () => {
    const mql = mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.resolved).toBe("dark");
    act(() => mql._emit(false));
    expect(result.current.resolved).toBe("light");
  });

  it("cycles light -> dark -> system -> light", () => {
    mockMatchMedia(true);
    const { result } = renderHook(() => useTheme(), { wrapper });
    act(() => result.current.setPreference("light"));
    act(() => result.current.cycle());
    expect(result.current.preference).toBe("dark");
    act(() => result.current.cycle());
    expect(result.current.preference).toBe("system");
    act(() => result.current.cycle());
    expect(result.current.preference).toBe("light");
  });

  it("reads a stored preference on init", () => {
    mockMatchMedia(true);
    localStorage.setItem("ai-dashboard.theme", "light");
    const { result } = renderHook(() => useTheme(), { wrapper });
    expect(result.current.preference).toBe("light");
    expect(result.current.resolved).toBe("light");
  });
});
```

- [ ] **Step 3: Run it to confirm it fails.**

Run: `pnpm exec vitest run --project unit src/__tests__/useTheme.test.tsx`
Expected: FAIL — cannot resolve `@/hooks/useTheme`.

- [ ] **Step 4: Implement the hook + provider.**

Create `frontend/src/hooks/useTheme.tsx`:

```tsx
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

function systemResolved(): ResolvedTheme {
  if (typeof window === "undefined" || !window.matchMedia) return "dark";
  return window.matchMedia(MEDIA).matches ? "dark" : "light";
}

function readPreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  const v = window.localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" || v === "system" ? v : "system";
}

function resolve(pref: ThemePreference): ResolvedTheme {
  return pref === "system" ? systemResolved() : pref;
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
  const [preference, setPreference] = useState<ThemePreference>(() => readPreference());
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolve(readPreference()));

  // Apply + persist whenever the preference changes.
  useEffect(() => {
    const r = resolve(preference);
    setResolved(r);
    applyTheme(r);
    try {
      window.localStorage.setItem(STORAGE_KEY, preference);
    } catch {
      /* storage unavailable — ignore */
    }
  }, [preference]);

  // Follow the OS while in "system".
  useEffect(() => {
    if (preference !== "system" || typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(MEDIA);
    const onChange = () => {
      const r = systemResolved();
      setResolved(r);
      applyTheme(r);
    };
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
```

- [ ] **Step 5: Run the tests to confirm they pass.**

Run: `pnpm exec vitest run --project unit src/__tests__/useTheme.test.tsx`
Expected: PASS (7 tests).

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/hooks/useTheme.tsx frontend/src/__tests__/useTheme.test.tsx frontend/src/__tests__/setup.ts
git commit -m "feat(frontend): useTheme hook + ThemeProvider with system following"
```

---

## Task 4: Mount the provider

**Files:**
- Modify: `frontend/src/main.tsx`

- [ ] **Step 1: Wrap `<App/>` with `<ThemeProvider>`.**

In `frontend/src/main.tsx`, add the import and wrap the tree (ThemeProvider outermost, inside `StrictMode`):

```tsx
import { ThemeProvider } from "./hooks/useTheme";
```

```tsx
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <WebSocketProvider>
          <App />
        </WebSocketProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
```

- [ ] **Step 2: Verify the app still boots and the full unit suite is green.**

Run: `pnpm exec vitest run --project unit`
Expected: PASS (no regressions). Load the app — still dark by default.

- [ ] **Step 3: Commit.**

```bash
git add frontend/src/main.tsx
git commit -m "feat(frontend): mount ThemeProvider at the app root"
```

---

## Task 5: `chartTheme` color helper

**Files:**
- Create: `frontend/src/lib/chartTheme.ts`
- Test: `frontend/src/__tests__/chartTheme.test.ts`

- [ ] **Step 1: Write the failing test.**

Create `frontend/src/__tests__/chartTheme.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { lightweightLayout, rechartsColors } from "@/lib/chartTheme";

describe("chartTheme", () => {
  it("returns distinct lightweight-charts backgrounds per theme", () => {
    expect(lightweightLayout("dark").layout.background.color).not.toBe(
      lightweightLayout("light").layout.background.color,
    );
  });

  it("uses the expected lightweight-charts backgrounds", () => {
    expect(lightweightLayout("dark").layout.background.color.toLowerCase()).toBe("#0a0a0a");
    expect(lightweightLayout("light").layout.background.color.toLowerCase()).toBe("#f5f2ea");
  });

  it("provides distinct recharts colors per theme", () => {
    expect(rechartsColors("dark").tickText).not.toBe(rechartsColors("light").tickText);
    expect(rechartsColors("light").heatmapEmpty).toContain("0,0,0");
    expect(rechartsColors("dark").heatmapEmpty).toContain("255,255,255");
  });
});
```

- [ ] **Step 2: Run it to confirm it fails.**

Run: `pnpm exec vitest run --project unit src/__tests__/chartTheme.test.ts`
Expected: FAIL — cannot resolve `@/lib/chartTheme`.

- [ ] **Step 3: Implement the helper.**

Create `frontend/src/lib/chartTheme.ts`:

```ts
import type { ResolvedTheme } from "@/hooks/useTheme";

/** lightweight-charts layout/grid options. */
export function lightweightLayout(theme: ResolvedTheme) {
  const c =
    theme === "light"
      ? { background: "#f5f2ea", textColor: "#2e2a22", grid: "#e2dccd" }
      : { background: "#0a0a0a", textColor: "#d0d0d0", grid: "#1a1a1a" };
  return {
    layout: { background: { color: c.background }, textColor: c.textColor },
    grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
  };
}

export interface RechartsColors {
  axis: string;
  cursor: string;
  tickText: string;
  dotStroke: string;
  heatmapEmpty: string;
}

export function rechartsColors(theme: ResolvedTheme): RechartsColors {
  return theme === "light"
    ? {
        axis: "rgba(160,111,44,0.30)",
        cursor: "rgba(160,111,44,0.45)",
        tickText: "#5c5648",
        dotStroke: "#f5f2ea",
        heatmapEmpty: "rgba(0,0,0,0.04)",
      }
    : {
        axis: "rgba(200,150,88,0.15)",
        cursor: "rgba(200,150,88,0.40)",
        tickText: "#9ea3b3",
        dotStroke: "#0b0d12",
        heatmapEmpty: "rgba(255,255,255,0.04)",
      };
}
```

- [ ] **Step 4: Run the test to confirm it passes.**

Run: `pnpm exec vitest run --project unit src/__tests__/chartTheme.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/lib/chartTheme.ts frontend/src/__tests__/chartTheme.test.ts
git commit -m "feat(frontend): theme-aware chart color helper"
```

---

## Task 6: `ThemeToggle` component

**Files:**
- Create: `frontend/src/components/ThemeToggle.tsx`
- Create: `frontend/src/components/ThemeToggle.stories.tsx`
- Test: `frontend/src/__tests__/ThemeToggle.test.tsx`

- [ ] **Step 1: Write the failing test.**

Create `frontend/src/__tests__/ThemeToggle.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import ThemeToggle from "@/components/ThemeToggle";
import { ThemeProvider } from "@/hooks/useTheme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.className = "dark";
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: true,
      media: "",
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  );
});

const wrap = (ui: ReactNode) => render(<ThemeProvider>{ui}</ThemeProvider>);

describe("ThemeToggle", () => {
  it("renders an accessible label reflecting the preference", () => {
    wrap(<ThemeToggle />);
    const btn = screen.getByTestId("theme-toggle");
    expect(btn).toHaveAttribute("data-preference", "system");
    expect(btn.getAttribute("aria-label")).toMatch(/system/i);
  });

  it("cycles the preference on click", async () => {
    const user = userEvent.setup();
    wrap(<ThemeToggle />);
    const btn = screen.getByTestId("theme-toggle");
    await user.click(btn); // system -> light
    expect(btn).toHaveAttribute("data-preference", "light");
    await user.click(btn); // light -> dark
    expect(btn).toHaveAttribute("data-preference", "dark");
    await user.click(btn); // dark -> system
    expect(btn).toHaveAttribute("data-preference", "system");
  });
});
```

- [ ] **Step 2: Run it to confirm it fails.**

Run: `pnpm exec vitest run --project unit src/__tests__/ThemeToggle.test.tsx`
Expected: FAIL — cannot resolve `@/components/ThemeToggle`.

- [ ] **Step 3: Implement the component.**

Create `frontend/src/components/ThemeToggle.tsx`:

```tsx
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
```

- [ ] **Step 4: Run the test to confirm it passes.**

Run: `pnpm exec vitest run --project unit src/__tests__/ThemeToggle.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Add the Storybook story.**

Create `frontend/src/components/ThemeToggle.stories.tsx`:

```tsx
import type { Meta, StoryObj } from "@storybook/react-vite";
import ThemeToggle from "./ThemeToggle";
import { ThemeProvider } from "@/hooks/useTheme";

const meta = {
  title: "Layout/ThemeToggle",
  component: ThemeToggle,
  parameters: { layout: "centered" },
  decorators: [(Story) => (<ThemeProvider><Story /></ThemeProvider>)],
} satisfies Meta<typeof ThemeToggle>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Cycles Light → Dark → System on click. */
export const Default: Story = {};
```

- [ ] **Step 6: Commit.**

```bash
git add frontend/src/components/ThemeToggle.tsx frontend/src/components/ThemeToggle.stories.tsx frontend/src/__tests__/ThemeToggle.test.tsx
git commit -m "feat(frontend): ThemeToggle control (light/dark/system)"
```

---

## Task 7: Wire the toggle into the UI (TopNav + Cmd-K)

**Files:**
- Modify: `frontend/src/components/layout/TopNav.tsx`
- Modify: `frontend/src/components/layout/AppLayout.tsx`

- [ ] **Step 1: Mount the toggle in TopNav's right cluster.**

In `frontend/src/components/layout/TopNav.tsx`, add the import:

```tsx
import ThemeToggle from "@/components/ThemeToggle";
```

Then, in the right-hand cluster, add `<ThemeToggle />` immediately before `<NotificationBell />`:

```tsx
          <span className="hidden md:inline-flex items-center gap-1.5">
            <ConnectionStatusDot />
          </span>
          <ThemeToggle />
          <NotificationBell />
```

- [ ] **Step 2: Add a "Toggle theme" command to the palette.**

In `frontend/src/components/layout/AppLayout.tsx`, add the import:

```tsx
import { useTheme } from "@/hooks/useTheme";
```

In `useDefaultCommands()`, call the hook and add the command + dep:

```tsx
function useDefaultCommands(): Command[] {
  const nav = useNavigate();
  const { cycle } = useTheme();
  return useMemo(
    () => [
      // …existing commands unchanged…
      { id: "go-theses", label: "Go to Theses", keywords: "thesis decision call",
        run: () => nav("/theses") },
      { id: "toggle-theme", label: "Toggle theme", keywords: "light dark system appearance mode",
        run: cycle },
    ],
    [nav, cycle],
  );
}
```

- [ ] **Step 3: Verify the full unit suite + the working toggle.**

Run: `pnpm exec vitest run --project unit`
Expected: PASS.
Load the app: the toggle appears in the top bar. Click it through System → Light → Dark and confirm the whole UI re-themes (page, surfaces, nav, analytics/command-palette via the slate alias). Open Cmd-K, run "Toggle theme". Reload — the choice persists.

**This is the milestone: light mode works end-to-end.** Tune the palette values from Task 1 live now if anything reads off (contrast, surface lift) before polishing charts/legacy.

- [ ] **Step 4: Commit.**

```bash
git add frontend/src/components/layout/TopNav.tsx frontend/src/components/layout/AppLayout.tsx
git commit -m "feat(frontend): expose theme toggle in TopNav + command palette"
```

---

## Task 8: Theme the lightweight-charts component (+ keep capture dark)

**Files:**
- Modify: `frontend/src/__tests__/setup.ts`
- Modify: `frontend/src/components/Chart.tsx`
- Modify: `frontend/src/pages/RenderChart.tsx`

- [ ] **Step 0: Teach the chart mock about `applyOptions`.**

`Chart` will start calling `chart.applyOptions(...)`. In `frontend/src/__tests__/setup.ts`, add `applyOptions: vi.fn(),` to the object returned by the mocked `createChart` (alongside `resize`/`remove`), or Chart-rendering tests throw `applyOptions is not a function`:

```ts
vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => ({
    addCandlestickSeries: vi.fn(() => ({ setData: vi.fn() })),
    timeScale: vi.fn(() => ({ fitContent: vi.fn() })),
    applyOptions: vi.fn(),
    resize: vi.fn(),
    remove: vi.fn(),
  })),
}));
```

- [ ] **Step 1: Make `Chart` theme-aware via an optional prop.**

In `frontend/src/components/Chart.tsx`, add imports:

```tsx
import { useTheme, type ResolvedTheme } from "@/hooks/useTheme";
import { lightweightLayout } from "@/lib/chartTheme";
```

Add `theme` to `ChartProps`:

```tsx
export interface ChartProps {
  ticker: string;
  timeframe: string;
  bars: number;
  theme?: ResolvedTheme;
  onReady?: () => void;
}
```

In the component body, after the `useQuery` call, resolve the active theme:

```tsx
  const { resolved } = useTheme();
  const activeTheme = theme ?? resolved;
```

Bake the initial theme into `createChart` (so there's no one-frame white flash — `useEffect` runs after paint). The effect is intentionally run-once, so silence exhaustive-deps:

```tsx
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;
    chartRef.current = createChart(containerRef.current, {
      autoSize: true,
      ...lightweightLayout(activeTheme),
    });
    seriesRef.current = chartRef.current.addCandlestickSeries();
    return () => {
      chartRef.current?.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

Add a new effect (immediately after the create effect) that re-applies colors when the theme *changes*:

```tsx
  useEffect(() => {
    chartRef.current?.applyOptions(lightweightLayout(activeTheme));
  }, [activeTheme]);
```

(Destructure `theme` in the params: `export default function Chart({ ticker, timeframe, bars, theme, onReady }: ChartProps) {`.)

- [ ] **Step 2: Pin the capture route to dark.**

In `frontend/src/pages/RenderChart.tsx`, add `useEffect` to the import and force dark on mount + pass `theme="dark"`:

```tsx
import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import Chart from "@/components/Chart";

function signalRenderReady(): void {
  document.body.dataset.renderReady = "true";
}

export default function RenderChart() {
  const [params] = useSearchParams();
  const ticker = params.get("ticker") ?? "SPY";
  const timeframe = params.get("timeframe") ?? "5m";
  const bars = Number(params.get("bars") ?? "60");

  // Deterministic capture: the headless context has no saved preference, so
  // force dark regardless of what the bootstrap resolved.
  useEffect(() => {
    const r = document.documentElement;
    r.classList.add("dark");
    r.classList.remove("light");
  }, []);

  return (
    <div style={{ width: "100vw", height: "100vh", background: "#0a0a0a" }}>
      <Chart ticker={ticker} timeframe={timeframe} bars={bars} theme="dark" onReady={signalRenderReady} />
    </div>
  );
}
```

- [ ] **Step 3: Verify.**

Run: `pnpm exec vitest run --project unit`
Expected: PASS (Chart tests use the mocked `createChart`, unaffected).
In the app, toggle to light and view a chart page (e.g. Market Ticker) — the chart background/grid follow the theme. Confirm `/render/chart?ticker=SPY` stays dark.

- [ ] **Step 4: Commit.**

```bash
git add frontend/src/components/Chart.tsx frontend/src/pages/RenderChart.tsx
git commit -m "feat(frontend): theme-aware lightweight-charts; keep capture dark"
```

---

## Task 9: Theme recharts + heatmap + ticker container

**Files:**
- Modify: `frontend/src/components/costs/DailyCostChart.tsx`
- Modify: `frontend/src/components/analytics/TriggerHeatmapCard.tsx`
- Modify: `frontend/src/pages/MarketTickerPage.tsx`

- [ ] **Step 1: Theme `DailyCostChart` (recharts).**

In `frontend/src/components/costs/DailyCostChart.tsx`, add:

```tsx
import { useTheme } from "@/hooks/useTheme";
import { rechartsColors } from "@/lib/chartTheme";
```

Inside the component (top of the render function body), add:

```tsx
  const c = rechartsColors(useTheme().resolved);
```

Then replace the hardcoded dark-assuming colors (keep the copper gradient stops `#c89658`/`#e6ad5e` — they read on both themes):

- `axisLine={{ stroke: "rgba(200,150,88,0.15)" }}` → `axisLine={{ stroke: c.axis }}`
- `cursor={{ stroke: "rgba(200,150,88,0.4)", strokeDasharray: "2 2" }}` → `cursor={{ stroke: c.cursor, strokeDasharray: "2 2" }}`
- `activeDot={{ r: 3, fill: "#e6ad5e", stroke: "#0b0d12", strokeWidth: 2 }}` → `activeDot={{ r: 3, fill: "#e6ad5e", stroke: c.dotStroke, strokeWidth: 2 }}`
- If any `<XAxis>`/`<YAxis>` has a `tick={{ fill: "<hardcoded>" }}` or `tickLine`/`stroke`, set the fill to `c.tickText`. (Read the file and apply to each axis present.)

- [ ] **Step 2: Theme the heatmap empty-cell wash.**

In `frontend/src/components/analytics/TriggerHeatmapCard.tsx`, add the same two imports, compute `const c = rechartsColors(useTheme().resolved);` in the component body, and replace the empty-cell color `"rgba(255,255,255,0.04)"` with `c.heatmapEmpty`. (The filled-cell copper-intensity colors stay — copper reads on both.)

- [ ] **Step 3: Theme the ticker page container.**

In `frontend/src/pages/MarketTickerPage.tsx`, change the chart container background from `background: "#0a0a0a"` to `background: "var(--ink-950)"` (inline `var()` themes automatically — no hook needed).

- [ ] **Step 4: Verify.**

Run: `pnpm exec vitest run --project unit`
Expected: PASS.
In light mode, open Costs (DailyCostChart), Analytics (TriggerHeatmap), and Market Ticker — axes/grid/cells/container read correctly on paper.

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/components/costs/DailyCostChart.tsx frontend/src/components/analytics/TriggerHeatmapCard.tsx frontend/src/pages/MarketTickerPage.tsx
git commit -m "feat(frontend): theme recharts cost chart, trigger heatmap, ticker container"
```

---

## Task 10: Convert inline-hex components to tokens

**Files:**
- Modify: `frontend/src/components/NewsFeed.tsx`
- Modify: `frontend/src/components/OptionChainTable.tsx`
- Modify: `frontend/src/components/ChartCaptureButton.tsx`

These use inline `style={{ … }}` hex that config aliasing can't reach. Replace hex with `var(--…)` so they theme automatically. Read each file and apply:

- [ ] **Step 1: `NewsFeed.tsx`.**
  - `color: "#888"` → `color: "var(--ink-400)"`
  - `borderBottom: "1px solid #222"` → `borderBottom: "1px solid var(--rule-soft)"`
  - `color: "#999"` → `color: "var(--ink-400)"`
  - link `color: "#9ecbff"` → `color: "var(--copper-300)"`
  - `color: "#bbb"` → `color: "var(--ink-300)"`

- [ ] **Step 2: `OptionChainTable.tsx`.**
  - `color: "#888"` → `color: "var(--ink-400)"`
  - selected/unselected `background: d === selected ? "#2a2a2a" : "#111"` → `d === selected ? "var(--ink-700)" : "var(--ink-900)"`
  - `color: "#fff"` → `color: "var(--ink-100)"`
  - borders `"1px solid #333"` → `"1px solid var(--rule)"`
  - ATM row `background: isAtm ? "#1a2a3a" : "transparent"` → `isAtm ? "color-mix(in srgb, var(--copper-500) 14%, transparent)" : "transparent"`

- [ ] **Step 3: `ChartCaptureButton.tsx`.**
  - `background: "rgba(20,20,20,0.7)"` → `background: "color-mix(in srgb, var(--ink-900) 82%, transparent)"`
  - `color: "#fff"` → `color: "var(--ink-100)"`
  - border `"1px solid #333"` → `"1px solid var(--rule)"`

- [ ] **Step 4: Verify.**

Run: `pnpm exec vitest run --project unit`
Expected: PASS.
In light mode, open a snapshot/thread view showing news + option chain + a chart capture button — all legible on paper, dark unchanged.

- [ ] **Step 5: Commit.**

```bash
git add frontend/src/components/NewsFeed.tsx frontend/src/components/OptionChainTable.tsx frontend/src/components/ChartCaptureButton.tsx
git commit -m "feat(frontend): token-ize inline-styled NewsFeed/OptionChain/CaptureButton"
```

---

## Task 11: Fix dark-tinted chromatic banners (light-base + dark: overrides)

Now that the `dark`/`light` class drives `darkMode: "class"`, the `bg-{color}-950/40 text-{color}-200` patterns (designed for a dark bg) get a light base + a `dark:` override. Read each file and apply.

**Files:**
- Modify: `frontend/src/pages/SnapshotComposerPage.tsx`
- Modify: `frontend/src/pages/ThreadDetailPage.tsx`

- [ ] **Step 1: `SnapshotComposerPage.tsx` alert banners.**
  - Warning (status) banner: `"rounded border border-amber-700/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200"` → `"rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:border-amber-700/50 dark:bg-amber-950/40 dark:text-amber-200"`
  - Error (alert) banner: `"rounded border border-red-700/50 bg-red-950/40 px-3 py-2 text-sm text-red-200"` → `"rounded border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-800 dark:border-red-700/50 dark:bg-red-950/40 dark:text-red-200"`

- [ ] **Step 2: `ThreadDetailPage.tsx` role/status badges.** Each `text-{c}-400 border-{c}-800 bg-{c}-950/40` triple → light base + dark override:
  - emerald: `"text-emerald-700 border-emerald-500/40 bg-emerald-500/10 dark:text-emerald-400 dark:border-emerald-800 dark:bg-emerald-950/40"`
  - amber: `"text-amber-700 border-amber-500/40 bg-amber-500/10 dark:text-amber-400 dark:border-amber-800 dark:bg-amber-950/40"`
  - violet: `"text-violet-700 border-violet-500/40 bg-violet-500/10 dark:text-violet-400 dark:border-violet-800 dark:bg-violet-950/40"`

  Preserve the surrounding conditional/JSX structure exactly — only the class strings change.

- [ ] **Step 3: Verify.**

Run: `pnpm exec vitest run --project unit`
Expected: PASS.
In light mode, trigger a snapshot warning/error banner and view a thread with role badges — tinted (not dark-blob) on paper; dark mode unchanged.

- [ ] **Step 4: Commit.**

```bash
git add frontend/src/pages/SnapshotComposerPage.tsx frontend/src/pages/ThreadDetailPage.tsx
git commit -m "feat(frontend): light-aware chromatic alert banners and badges"
```

---

## Task 12: Chromatic text & foreground contrast (light-base + dark:)

Colored *fill buttons* (`bg-emerald-600`, `bg-indigo-600`) render fine on paper and stay. But chromatic *text* (`text-{c}-300/400`) is low-contrast on cream, and `text-white` used as a foreground on a light surface (active tabs) is invisible. Fix each with a darker light base + a `dark:` override that preserves the current dark look.

**Convention:** `text-{c}-400` → `text-{c}-700 dark:text-{c}-400`; `text-{c}-300` → `text-{c}-700 dark:text-{c}-300`; hover variants get a matching `dark:hover:`. Read each file and apply precisely, keeping surrounding JSX/conditionals intact.

**Files:**
- Modify: `frontend/src/pages/TriggersListPage.tsx`
- Modify: `frontend/src/pages/TriggerEditorPage.tsx`
- Modify: `frontend/src/pages/ThesisDetailPage.tsx`
- Modify: `frontend/src/pages/SnapshotCostPage.tsx`
- Modify: `frontend/src/pages/WatchlistsList.tsx`
- Modify: `frontend/src/pages/WatchlistDetail.tsx`

- [ ] **Step 1: `TriggersListPage.tsx`.**
  - `hover:text-indigo-400` → `hover:text-indigo-700 dark:hover:text-indigo-400`
  - `text-indigo-400 hover:text-indigo-300` → `text-indigo-700 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-300`
  - `text-rose-400 hover:text-rose-300` → `text-rose-700 hover:text-rose-600 dark:text-rose-400 dark:hover:text-rose-300`
  - `text-amber-400 hover:text-amber-300` → `text-amber-700 hover:text-amber-600 dark:text-amber-400 dark:hover:text-amber-300`

- [ ] **Step 2: `TriggerEditorPage.tsx`.**
  - Active tab labels (3 occurrences — condition / firings / backtest): `text-white border-b-2 border-indigo-500` → `text-ink-900 border-b-2 border-indigo-500 dark:text-white`
  - `text-emerald-400` (matched) → `text-emerald-700 dark:text-emerald-400`
  - `text-rose-400` (invalid condition + error message, 2 spots) → `text-rose-700 dark:text-rose-400`
  - The inactive-tab `text-neutral-400` already themes via the `neutral→ink` alias — leave it.
  - The `bg-indigo-600 … text-white` submit buttons are fill buttons — leave them.

- [ ] **Step 3: `ThesisDetailPage.tsx`.**
  - `pm.forward_return_pct >= 0 ? "text-emerald-300" : "text-rose-300"` → `pm.forward_return_pct >= 0 ? "text-emerald-700 dark:text-emerald-300" : "text-rose-700 dark:text-rose-300"`
  - `text-emerald-400` (positive list item) → `text-emerald-700 dark:text-emerald-400`
  - `text-rose-400` (negative list item) → `text-rose-700 dark:text-rose-400`

- [ ] **Step 4: `SnapshotCostPage.tsx`.**
  - `text-rose-400` → `text-rose-700 dark:text-rose-400`

- [ ] **Step 5: `WatchlistsList.tsx` and `WatchlistDetail.tsx`.**
  - `text-rose-400` → `text-rose-700 dark:text-rose-400` (preserve the other classes on the same element, e.g. `text-sm hover:underline`).

- [ ] **Step 6: Verify.**

Run: `pnpm exec vitest run --project unit`
Expected: PASS.
In light mode, open Triggers list, the Trigger editor (click each tab — active label is visible), a Thesis detail with a post-mortem, Snapshot cost, and Watchlists — all chromatic text is legible; dark mode unchanged.

- [ ] **Step 7: Commit.**

```bash
git add frontend/src/pages/TriggersListPage.tsx frontend/src/pages/TriggerEditorPage.tsx frontend/src/pages/ThesisDetailPage.tsx frontend/src/pages/SnapshotCostPage.tsx frontend/src/pages/WatchlistsList.tsx frontend/src/pages/WatchlistDetail.tsx
git commit -m "feat(frontend): light-aware chromatic text & active-tab foregrounds"
```

---

## Task 13: Final verification + live palette tuning

**Files:** none (verification), plus possible tuning of `frontend/src/styles/globals.css` Task-1 values.

- [ ] **Step 1: Full check.**

Run: `pnpm exec tsc --noEmit && pnpm run lint && pnpm exec vitest run --project unit`
Expected: all PASS.

- [ ] **Step 2: Light-mode walkthrough.** Visit each top-level route (Dashboard, Snapshot, Threads, a Thread detail, Triggers, Trigger editor, Schedules, Costs, Analytics, Theses, Settings, Watchlists) in light mode. Note any low-contrast text or off-looking surface and adjust the `html.light` token values in Task 1. Re-check with browser DevTools contrast (target WCAG AA for body text and the copper text steps). Verify the toggle, persistence across reload, and OS-following in System mode.

- [ ] **Step 3: Confirm chromatic coverage.** Chromatic text and active-tab foregrounds are themed (Task 12); the dark-tinted banners/badges are themed (Task 11). Only colored *fill buttons* (`bg-emerald-600`, `bg-indigo-600`) are intentionally retained — legible on both themes; recoloring them to copper would be a brand change beyond this scope.

- [ ] **Step 4: Commit any tuning.**

```bash
git add frontend/src/styles/globals.css
git commit -m "fix(frontend): tune light palette for contrast"
```

---

## Spec coverage map

| Spec section | Task |
|---|---|
| §1 Theme model (class, color-scheme, meta) | 1, 3 |
| §2 No-flash bootstrap | 2 |
| §3 ThemeProvider + useTheme (provider-safe) | 3, 4 |
| §4 Light palette + overloaded-token seams + atmosphere | 1 (+ tuning in 13) |
| §5 Charts (chartTheme, applyOptions) | 5, 8, 9 |
| §6 /render/chart stays dark | 8 |
| §7 + Plan-time refinement: slate/neutral aliasing, inline-hex, chromatic banners & text | 1, 10, 11, 12 |
| §8 Toggle UI (TopNav + Cmd-K) | 6, 7 |
| Testing (useTheme, ThemeToggle, chartTheme, matchMedia mock) | 3, 5, 6 |
| Out of scope (E2E baselines, server persistence) | acknowledged in 13 |
