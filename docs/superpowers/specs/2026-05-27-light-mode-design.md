# Light Mode — design

**Date:** 2026-05-27
**Status:** Approved (brainstorm) → ready for plan
**Scope:** Frontend only. No Django / API / model changes.

## Summary

Add a toggle-able **light theme** ("warm paper / newsprint") alongside the existing
dark "Ledger" terminal aesthetic. The design system is already token-driven and
dark-first, so light mode is delivered primarily by **redefining the existing CSS
custom properties under an `html.light` selector** — no broad component rewrite.
A small amount of additional work covers the surfaces that bypass the token system
(charts configured in JS, a few legacy inline-styled components, the body
atmosphere). A three-way **Light / Dark / System** control lives in `TopNav`,
persists to `localStorage`, follows the OS on first visit, and avoids a
flash-of-wrong-theme via an inline bootstrap script.

## Goals

- A light theme that looks intentional (warm paper, retained copper accents), not an auto-inverted dark theme.
- Toggle with three states: **Light**, **Dark**, **System** (System defers to the OS and live-updates).
- First visit with no saved preference **follows the OS** (`prefers-color-scheme`); any manual choice is remembered and wins thereafter.
- No flash of the wrong theme on load.
- Full polish: charts and the few legacy inline-styled components also theme correctly — nothing looks broken in light mode.

## Non-goals

- Server-side / per-user persisted theme. Persistence is `localStorage` only (matches the single-user model).
- Re-theming the `/render/chart` capture route — it **stays dark** for deterministic PNG capture (see §6).
- Adding light-mode E2E visual baselines in this pass (see §9).
- A semantic-token refactor (`--bg`/`--surface`/`--text`). Explicitly rejected — see "Approach".

## Plan-time refinement (2026-05-27)

Enumerating the codebase during planning revealed the component-theming surface is larger than §7 first assumed, and surfaced a cleaner mechanism. This refines — not replaces — the chosen approach.

- **~201 raw `slate-*` / `neutral-*` color-class usages** (analytics cards, `CommandPalette`, `ShortcutHelpDialog`, `EmptyState`, `ErrorBoundary`, `Skeleton`, `ThesisBadges`, …) bypass the token system and would stay dark. **Fix centrally:** alias the `slate` and `neutral` Tailwind color scales to `var(--ink-*)` in `tailwind.config.ts` — exactly how `ink`/`copper`/`gain`/`loss` are already defined. Zero component edits; dark mode also becomes more token-consistent. Opacity modifiers on these var-based colors already work in this repo (`TopNav` uses `bg-copper-500/0 group-hover:bg-copper-500/20`), so `bg-slate-700/50` etc. alias cleanly.
- **Inline `style={{…}}` hex** in `NewsFeed`, `OptionChainTable`, `MarketTickerPage` (container) can't be reached by config aliasing → manual token conversion. (`RenderChart` stays dark per §6.)
- **Chromatic state colors** (`emerald`/`rose`/`amber`/`indigo`/`violet`): the dark-tinted alert/badge banners (`bg-{amber,red,emerald,violet}-950/40 text-*-200`) on `SnapshotComposerPage` and `ThreadDetailPage` would look broken on paper. Because the new `dark`/`light` class drives Tailwind's existing `darkMode: "class"`, these are fixed with **light-base + `dark:` overrides**. Plain chromatic buttons/links (`bg-emerald-600`, `text-rose-400` on secondary Trigger/Watchlist pages) remain legible on both themes and are an **accepted limitation / follow-up** to keep this pass bounded.

## Approach (and rejected alternatives)

**Chosen — variable-swap under `html.light`.** Keep the current `:root { … }` dark
tokens as the default. Add an `html.light { … }` block that redefines the same
`--ink-*` / `--copper-*` / market / `--rule-*` variables with light values. Because
every Tailwind color utility (`bg-ink-950`, `text-ink-100`, …) and every `.ledger-*`
component class resolves through these variables — including inside `color-mix()`
expressions — flipping the definitions at `<html>` re-themes the bulk of the app
with **no component edits**.

- *Rejected — semantic token layer:* introduce `--bg`/`--surface`/`--text` and migrate every component off `bg-ink-950`/`text-ink-100`. Clean in theory, but a churny rewrite across dozens of files for no functional gain. Violates "follow existing patterns / don't refactor unrelated code."
- *Rejected — per-component `dark:`/`light:` Tailwind variants:* the app uses **zero** Tailwind color variants today; adopting them means touching every component. The central variable-swap achieves the same result.

## Architecture

### 1. Theme model

- The resolved theme is carried as a **class on `<html>`**: `dark` (default) or `light`. This reuses the existing `<html class="dark">` and the already-configured `darkMode: "class"` in `tailwind.config.ts`, rather than introducing a parallel `data-theme` attribute.
- Two distinct concepts:
  - **preference** — `"light" | "dark" | "system"`, persisted to `localStorage["ai-dashboard.theme"]` (mirrors the `useSidebarCollapsed` key convention).
  - **resolved** — `"light" | "dark"`, the concrete theme actually applied. `system` resolves via `matchMedia("(prefers-color-scheme: dark)")` and live-updates on OS change.
- `color-scheme` is set per theme (`:root { color-scheme: dark }` / `html.light { color-scheme: light }`) so native scrollbars / form controls / date pickers match. The `<meta name="color-scheme">` and `<meta name="theme-color">` tags are updated to track the resolved theme.

### 2. No flash-of-wrong-theme (bootstrap)

An inline, render-blocking `<script>` in `index.html` `<head>` runs before React mounts:

```html
<script>
  (function () {
    try {
      var pref = localStorage.getItem("ai-dashboard.theme") || "system";
      var dark = pref === "dark" ||
        (pref === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
      var root = document.documentElement;
      root.classList.toggle("dark", dark);
      root.classList.toggle("light", !dark);
      root.style.colorScheme = dark ? "dark" : "light";
    } catch (e) { /* default: leave class="dark" */ }
  })();
</script>
```

The static `class="dark"` on `<html>` remains as the safe fallback if the script fails or storage is unavailable.

### 3. State — `ThemeProvider` + `useTheme`

New `frontend/src/hooks/useTheme.tsx` (provider + hook, mirroring `hooks/useToast.tsx`):

```ts
type ThemePreference = "light" | "dark" | "system";
type ResolvedTheme = "light" | "dark";

interface ThemeContextValue {
  preference: ThemePreference;
  resolved: ResolvedTheme;
  setPreference: (p: ThemePreference) => void;
  cycle: () => void; // light → dark → system → light
}
```

- `ThemeProvider` is mounted in `main.tsx`, wrapping `<App />` alongside the existing providers.
- On mount and whenever `preference` changes: compute `resolved`, apply the `dark`/`light` class to `document.documentElement`, set `color-scheme`, update the two `<meta>` tags, and persist `preference`.
- When `preference === "system"`, subscribe to `matchMedia("(prefers-color-scheme: dark)")` `change` events and recompute `resolved` live; unsubscribe otherwise.
- **Safe without a provider:** the context default value is a working standalone implementation that reads the current `<html>` class (defaulting to `"dark"`) and treats `setPreference`/`cycle` as no-ops. This keeps components that call `useTheme()` (e.g. `Chart.tsx`) renderable in existing tests that don't wrap `ThemeProvider`. The provider upgrades the hook to the live, reactive version.

### 4. Light palette (token redefinitions under `html.light`)

Starting values for the "warm paper" theme — **tuned live in the running app against a WCAG-AA contrast checker.** The numbers preserve *role* (background vs text), not lightness.

**Ink scale** — backgrounds elevate whiter, text/recesses go darker:

| Var | Role | Dark (current) | Light (start) |
|---|---|---|---|
| `--ink-900` | elevated card | `#10131a` | `#fefdfa` |
| `--ink-850` | secondary surface | `#141823` | `#faf7f0` |
| `--ink-950` | page background | `#0b0d12` | `#f5f2ea` |
| `--ink-800` | chips / pill bg | `#171a23` | `#eae4d8` |
| `--ink-void` | recessed inset (inputs, code, kbd) | `#07080b` | `#e7e1d4` |
| `--ink-700` | — | `#222632` | `#d6cfbf` |
| `--ink-600` | — | `#2f3341` | `#bfb7a3` |
| `--ink-500` | faint | `#3a3e4c` | `#a39a85` |
| `--ink-400` | muted / placeholder | `#6b7081` | `#857d6b` |
| `--ink-300` | secondary text | `#9ea3b3` | `#5c5648` |
| `--ink-200` | prose body | `#c7ccd9` | `#2e2a22` |
| `--ink-100` | body text (html color) | `#e8eaf2` | `#1c1812` |
| `--ink-50` | bright / display headings | `#f5f6fb` | `#14110b` |

**Copper** — keep the rich button/focus fills; deepen the *text* steps for AA on paper:

| Var | Usage | Dark | Light (start) |
|---|---|---|---|
| `--copper-200` | accent text (active nav, prose em, pill) | `#f1ca8b` | `#6f4a17` |
| `--copper-300` | links, display em | `#e6ad5e` | `#855816` |
| `--copper-400` | eyebrow, CTA gradient top | `#d79642` | `#a06f2c` |
| `--copper-500` | focus ring, default accent | `#c89658` | `#b07e3e` |
| `--copper-600/700/800` | CTA gradient bottom, deep | unchanged | unchanged |

**Market** — deepen the text-facing `300` steps; `500` (used in border mixes) stays:

| Var | Dark | Light (start) |
|---|---|---|
| `--gain-300` | `#74cfa5` | `#1f7a52` |
| `--loss-300` | `#d48086` | `#b3322f` |

**Hairlines:** `--rule-soft` (= `ink-100` @ 8%) auto-corrects — `ink-100` is now near-black, so it becomes a faint dark line on paper (correct). `--rule` / `--rule-strong` (copper mixes) may need a small alpha bump for visibility on light; tune live.

**Overloaded-token seams (need explicit `html.light` overrides):**

- `--ink-void` is both "recessed inset background" *and* "dark text on the copper CTA" (`.ledger-cta { color: var(--ink-void) }`). In light it flips to a light inset, which would make CTA text unreadable. Override: `html.light .ledger-cta { color: var(--ink-50); }` (keep dark text on the copper button).
- `--copper-400` is both eyebrow **text** and the CTA gradient **fill** top stop. Deepening it for text is fine for the button too, but verify; if the button reads muddy, override `.ledger-cta` to use `--copper-500 → --copper-700` in light. Eyebrow/sub-label text that needs more contrast gets `html.light .ledger-eyebrow { color: var(--copper-700); }`.

**Atmosphere overrides under `html.light`:**

- `body` — replace the dark grain + dark radial washes with a paper base (`--ink-950`), a faint copper top wash, the cool/blue wash dropped or lightened, and the SVG grain either removed or re-tinted to a light "paper tooth" at low opacity.
- `.ledger-surface` — the current bottom-darkening gradient (`…, rgba(0,0,0,0.25)`) reads as dirty on a white card; replace with a faint top sheen (`linear-gradient(180deg, rgba(255,255,255,0.5), rgba(0,0,0,0.02))`). The copper top-edge `::before` highlight stays subtle.

### 5. Charts (theme-aware, JS-configured)

New `frontend/src/lib/chartTheme.ts` exporting color maps keyed by `ResolvedTheme`:

- `lightweightChartOptions(theme)` → `{ layout, grid }` for `lightweight-charts`.
- Recharts helpers → axis stroke, grid, tick text, tooltip, and the dark-assuming bits (e.g. the active-dot stroke `#0b0d12`, heatmap cell wash `rgba(255,255,255,0.04)`). Copper accent stops are kept (they read on both themes).

`Chart.tsx` gains an optional `theme?: ResolvedTheme` prop. When omitted it uses `useTheme().resolved`; it re-applies options reactively via `chart.applyOptions(...)` on theme change (no chart re-creation). Recharts consumers (`DailyCostChart`, analytics cards) read the resolved theme via `useTheme()` and derive colors from `chartTheme`.

### 6. `/render/chart` stays dark (determinism)

`RenderChart` imports the same `Chart.tsx` used in the UI. In the headless-capture context there's no `localStorage`, so a `system` preference would resolve via `matchMedia` — and headless Chromium often reports `light`, which would produce a light PNG. To keep captures deterministic:

- `RenderChart` passes `theme="dark"` to `Chart` explicitly.
- `RenderChart` pins the dark class on mount (`document.documentElement.classList.add("dark"); …remove("light")`) to neutralize whatever the bootstrap script set.
- Its existing `background:#0a0a0a` wrapper stays.

### 7. Legacy inline-styled component cleanup (full-polish scope)

Convert hardcoded inline hex to design-system classes / tokens so they theme for free *and* gain visual consistency:

- `components/NewsFeed.tsx` (`#888`, `#222`, `#999`, `#9ecbff`, `#bbb`)
- `components/OptionChainTable.tsx` (`#2a2a2a`, `#111`, `#fff`, `#333`, `#1a2a3a`)
- `components/ChartCaptureButton.tsx` (`rgba(20,20,20,0.7)`, `#fff`, `#333`)
- `components/analytics/TriggerHeatmapCard.tsx` (`rgba(255,255,255,0.04)` cell wash → theme-aware)
- `pages/MarketTickerPage.tsx` (`background:#0a0a0a` container → token)

### 8. Toggle UI

- New `frontend/src/components/ThemeToggle.tsx`: a compact icon button in `TopNav`'s right cluster (next to `NotificationBell`). Cycles **Light → Dark → System**, showing a sun / moon / auto glyph for the current preference, with a `title` + `aria-label` reflecting state (e.g. `"Theme: System (dark)"`). Styled with `.ledger-ghost` / existing icon-button conventions.
- Cmd-K command **"Toggle theme"** added via `AppLayout`'s default command list (`useDefaultCommands`), reusing `useTheme().cycle`.
- A `ThemeToggle.stories.tsx` Storybook story.

## Files

**Create**
- `frontend/src/hooks/useTheme.tsx` — `ThemeProvider` + `useTheme` (+ safe standalone default).
- `frontend/src/lib/chartTheme.ts` — theme-aware chart color maps.
- `frontend/src/components/ThemeToggle.tsx` — the toggle.
- `frontend/src/components/ThemeToggle.stories.tsx` — Storybook story.
- `frontend/src/__tests__/useTheme.test.tsx`
- `frontend/src/__tests__/ThemeToggle.test.tsx`

**Modify**
- `frontend/index.html` — inline no-FOUC bootstrap script.
- `frontend/src/styles/globals.css` — `html.light` token block + `color-scheme` + `body` / `.ledger-surface` / `.ledger-cta` / `.ledger-eyebrow` light overrides.
- `frontend/src/main.tsx` — wrap with `<ThemeProvider>`.
- `frontend/src/components/layout/TopNav.tsx` — mount `<ThemeToggle/>`.
- `frontend/src/components/layout/AppLayout.tsx` — add "Toggle theme" Cmd-K command.
- `frontend/src/components/Chart.tsx` — optional `theme` prop + reactive `applyOptions`.
- `frontend/src/pages/RenderChart.tsx` — pass `theme="dark"`, pin dark class.
- `frontend/src/pages/MarketTickerPage.tsx` — themed container.
- `frontend/src/components/costs/DailyCostChart.tsx` — theme-aware recharts colors.
- `frontend/src/components/analytics/TriggerHeatmapCard.tsx` — theme-aware cell wash. (Sweep `components/analytics/*` for other recharts hardcodes during implementation.)
- `frontend/src/components/NewsFeed.tsx`, `OptionChainTable.tsx`, `ChartCaptureButton.tsx` — inline hex → tokens.
- `frontend/src/__tests__/setup.ts` — default `window.matchMedia` mock.

## Testing

- **`useTheme.test.tsx`** (vitest): defaults to `system` with no stored pref; resolves `dark`/`light` from the `matchMedia` mock; `setPreference` persists to `localStorage`, applies the `<html>` class, and updates `resolved`; `system` recomputes on a `matchMedia` `change` event; an explicit `light`/`dark` preference ignores the OS; `cycle` goes light → dark → system → light.
- **`ThemeToggle.test.tsx`**: renders the current state; click cycles and updates `aria-label`/glyph; respects an injected preference.
- **`setup.ts`**: add a default `window.matchMedia` stub (`matches:false`, `addEventListener`/`removeEventListener`/`addListener`/`removeListener` no-ops) so the suite doesn't crash; `useTheme.test` overrides per-case via `vi.stubGlobal`.
- Existing tests stay green because `useTheme()` is provider-optional and `Chart.tsx`'s color path is mocked (`lightweight-charts` is stubbed in `setup.ts`).
- `make lint` (eslint + tsc) and the frontend `vitest` unit lane gate the work.

## Out of scope / follow-ups

- **Light-mode E2E visual baselines.** The visual lane currently captures dark; baselines are root-owned and regenerated via `make e2e-visual-update`. Adding light baselines is a separate, opt-in follow-up.
- **`/render/chart` light rendering** — intentionally never (deterministic capture).
- **Server-persisted / per-profile theme** — not in the single-user model.

## Risks & mitigations

- *Bootstrap script error → FOUC or no theme:* wrapped in `try/catch`; static `class="dark"` is the fallback.
- *Headless capture turning light:* mitigated by `Chart` `theme="dark"` prop + `RenderChart` pinning the dark class (§6).
- *Contrast regressions in light mode:* palette values are starting points, tuned live against an AA checker; copper/market text steps deepened deliberately.
- *Provider-context throw breaking existing tests:* `useTheme()` has a working non-throwing default (§3).
- *Overloaded tokens (`--ink-void`, `--copper-400`):* explicit `html.light` component overrides documented in §4.
