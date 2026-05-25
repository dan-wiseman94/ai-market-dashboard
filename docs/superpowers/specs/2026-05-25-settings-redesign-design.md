# Settings redesign — design

**Date:** 2026-05-25
**Status:** Proposed
**Topic:** Rebuild the Settings area into a coherent, Ledger-styled hub.

## Problem

The `/settings` page is the last significant un-migrated corner of the app. While
pages like `CostsPage` and `AnalyticsPage` use the polished **Ledger** design
system (copper/ink surfaces, serif display headings, eyebrow labels, mono tabular
numerics, copper CTAs), Settings still uses the stale raw `slate-*` palette and is
visibly inconsistent with the rest of the product.

Concrete problems with the current implementation:

- **Placeholder-only inputs, no `<label>`s** (`ProviderConfigCard.tsx`) — an
  accessibility defect and a usability one (the hint vanishes once you type).
- **No save feedback** — no pending/disabled state, no success/error toast, even
  though a `ToastProvider` is already mounted in `AppLayout`.
- **Free-text model field** — despite an existing catalog (`/api/schwab/models/`)
  and a `ProviderModelPicker` component.
- **Cramped 2-column grid** of tiny, low-contrast fields with no hierarchy.
- **Orphaned siblings** — `/settings/backups` and `/settings/export` already live
  under the `/settings/*` URL namespace, but they are absent from the `SideNav`
  and unlinked from the Settings page, so they are reachable only by typing the
  URL. They were also never migrated to the Ledger system.
- **Latent data-loss bug** — see "API key clearing bug" below.

## Goals

1. Bring the entire Settings cluster onto the Ledger design system.
2. Restructure `/settings` into a hub with a left sub-nav rail and child routes.
3. Fix the UX: labeled fields, catalog-backed model selection, save feedback,
   per-provider enable toggle, inline cost-cap usage meters, light validation.
4. Make Backups and Export discoverable and consistent.
5. Fix the API-key-clearing bug.

## Non-goals (YAGNI)

- **No backend changes.** Every endpoint and model already exists.
- **No new dependencies.** Reuse existing hooks, primitives, and design tokens.
- **No Finnhub/Marketaux credential UI** — there is no endpoint for it; the
  Connections section stays honest rather than padded.
- No theme switching, no global-cap concept (caps remain per-provider), no
  restructuring of the global `SideNav` beyond what discoverability requires.

## Decisions (confirmed with user)

- **Layout:** left sub-nav rail with **nested routes** (not tabs, not single-scroll).
- **Depth:** full — rebuild all four sections (AI Providers, Connections, Backups,
  Export) under one hub.
- **Enable toggle:** persists **immediately** (optimistic + toast); the API key /
  model / caps save behind an explicit **Save** button.

## Architecture

### Routing

`/settings` becomes a layout route rendering the hub chrome + `<Outlet/>`. The
four sections are children, preserving the existing `/settings/backups` and
`/settings/export` URLs and yielding correct nested breadcrumbs
(`Home / Settings / Backups`). Breadcrumbs already aggregate `handle.crumb` from
all matched routes (verified in `breadcrumbs.test.tsx`), so nesting is a strict
improvement.

```
{
  path: "settings",
  element: <SettingsLayout />,
  handle: { crumb: "Settings" },
  children: [
    { index: true,            element: <ProvidersSettings />,    handle: { crumb: "AI Providers" } },
    { path: "connections",    element: <ConnectionsSettings />,  handle: { crumb: "Connections" } },
    { path: "backups",        element: <BackupsPage />,          handle: { crumb: "Backups" } },
    { path: "export",         element: <ExportPage />,           handle: { crumb: "Export" } },
  ],
}
```

Because the rail surfaces Backups and Export, the orphaning problem is solved
without touching `SideNav`. (If desired later, adding them to `SideNav` is a
one-line change; out of scope here.)

### Component tree

```
SettingsLayout                      pages/settings/SettingsLayout.tsx
├─ page header (eyebrow + ledger-display title)
├─ SettingsNavRail                  (NavLink list; reuses SideNav's active copper hairline)
└─ <Outlet/>
     ├─ ProvidersSettings           pages/settings/ProvidersSettings.tsx
     │    └─ ProviderCard × 3        components/settings/ProviderCard.tsx
     │         ├─ Toggle             components/ui/Toggle.tsx
     │         ├─ Field × N          components/settings/Field.tsx
     │         ├─ ModelSelect        components/settings/ModelSelect.tsx
     │         └─ CapMeter × {1,2}   components/settings/CapMeter.tsx
     ├─ ConnectionsSettings         pages/settings/ConnectionsSettings.tsx
     ├─ BackupsPage (restyled)      pages/BackupsPage.tsx
     └─ ExportPage  (restyled)      pages/ExportPage.tsx
```

A shared `SettingsSection` (`components/settings/SettingsSection.tsx`) renders the
per-section eyebrow + title + optional header action, so all four sections share
chrome and the child pages shed their own `<main>`/`<h1>` wrappers.

## Section designs

### 1. AI Providers (`/settings`, index)

One `ProviderCard` per provider in `["claude", "openai", "local"]`:

- **Header row:** status dot (enabled → copper/gain, disabled → ink), provider
  display name (`Claude` / `OpenAI` / `Local`), a live `today: $0.0000` pill
  (from `useAiUsage`), and an **enabled** `Toggle` that persists immediately via
  `useUpsertProviderConfig` (optimistic; success/error toast).
- **Labeled fields** (each via `Field`, wiring `htmlFor`/`id`):
  - **API key** — `type="password"`. Accessible label **must** be
    `"<Provider> API key"` (e.g. `"Claude API key"`) to satisfy
    `e2e/pages/settings.py`. When a key is stored, show a "key is set ••••"
    indicator and placeholder "Paste to replace · leave blank to keep".
  - **Default model** — `ModelSelect`: a `<select>` of catalog models for the
    provider (`useAiModels(provider)`) plus a "Custom…" option revealing a text
    input. Local has no catalog models → defaults to the custom text input.
  - **Daily cap (USD)** — numeric; default `10.00`.
  - **Monthly cap (USD)** — numeric, optional; blank = no monthly limit.
  - **Base URL** — Local only; e.g. `http://host.docker.internal:11434/v1`.
- **Cap meters:** `CapMeter` bars for daily (and monthly, if set) showing
  spend-vs-cap, colored gain → copper → loss, sourced from `useCostsCaps`
  (`/api/costs/caps` → `CapRow{provider, daily{cap,spent,pct}, monthly|null}`).
- **Save:** copper `ledger-cta`, disabled while `isPending`, label flips to
  "Saving…". Success → toast "Claude settings saved" + reset draft; error →
  error toast. Validation: caps parse as non-negative numbers; model non-empty;
  Save disabled while invalid (inline message under the offending field).

#### API key clearing bug (fix folded in)

`ProviderConfigSerializer.update` pops `api_key_write`; if it is **not `None`** it
writes it to `instance.api_key`, and the model's setter maps `""` → `None`
(clears the stored key). The current card always sends
`api_key_write: draft.api_key_write ?? ""`, so **any save with an untouched key
field wipes the stored key**. Fix: only include `api_key_write` in the request
body when the user actually typed a value; omit it otherwise so the serializer
sees `None` and leaves the key intact.

### 2. Connections (`/settings/connections`)

A single rich Schwab card (rebuilt `SchwabConnectionCard`):

- Eyebrow "Brokerage", display "Charles Schwab".
- Status: **Connected** (gain) with `token refreshes in …` (`formatDistanceToNow`
  on `expires_at`) or **Not connected** (loss). Loading → `Skeleton`.
- One line on what it powers (quotes, OHLC, chains, positions).
- Connect / Reconnect CTA → `fetchSchwabAuthorizeUrl()` redirect.

### 3. Backups (`/settings/backups`) — restyle only

Keep all behavior and hooks (`useBackups`, `useRunBackupNow`, `useDeleteBackup`).
Move from slate `<main>`/`<h1>` to the shared `SettingsSection` + `ledger-surface`
rows, `ledger-pill` status, `ledger-cta`/`ledger-ghost` buttons, tabular sizes.

**Must preserve** (E2E contract, `e2e/pages/backups.py`): button accessible name
containing "Back up now"; `data-testid="backup-row-{id}"`; "Restore" button and
"Download" link within each row.

### 4. Export (`/settings/export`) — restyle only

Keep all behavior and hooks (`useExports`, `useCreateExport`, `useDeleteExport`).
Same Ledger treatment.

**Must preserve** (E2E contract, `e2e/pages/export.py`): button accessible name
"Start export"; `data-testid="export-row-{id}"`; "Download" link within each row.

## New reusable units

| Unit | Purpose | Depends on |
|---|---|---|
| `components/ui/Toggle.tsx` | Accessible switch: `role="switch"`, `aria-checked`, Space/Enter, focusable. | — |
| `components/settings/Field.tsx` | Label + optional hint + control (children); generates id, wires `htmlFor`/`aria-describedby`. | — |
| `components/settings/SettingsSection.tsx` | Section eyebrow + title + optional action. | — |
| `components/settings/ProviderCard.tsx` | One provider's full config + save lifecycle. | hooks, Toggle, Field, ModelSelect, CapMeter |
| `components/settings/ModelSelect.tsx` | Catalog dropdown + custom escape hatch. | `useAiModels` |
| `components/settings/CapMeter.tsx` | Single spend-vs-cap bar (extracted from `CostCapBars`'s `Bar`). | — |
| `pages/settings/SettingsLayout.tsx` | Hub shell: header + rail + Outlet. | react-router |
| `pages/settings/ProvidersSettings.tsx` | Renders the three `ProviderCard`s. | hooks |
| `pages/settings/ConnectionsSettings.tsx` | Schwab card. | `useSchwabStatus` |

## Data flow

No new endpoints. `useUpsertProviderConfig` is broadened to invalidate
`["provider-configs"]`, `["costs","caps"]`, and `["ai-usage"]` on success so the
pill and cap meters refresh. Toasts are pushed from `ProviderCard` (it has
`useToast`).

## Accessibility

- All inputs labeled via `Field`; API key labels exactly `"<Provider> API key"`.
- `Toggle` is a real switch (role, `aria-checked`, keyboard).
- Sub-nav rail is `<nav aria-label="Settings sections">`.
- Status conveyed by text, not color alone ("Connected", "73%").
- Targets the existing axe-core a11y lane (`e2e/a11y/test_axe_per_route.py`
  covers `/settings/backups` and `/settings/export`); labeled fields should
  remove existing violations rather than add any.

## Files

**Created:** `pages/settings/SettingsLayout.tsx`,
`pages/settings/ProvidersSettings.tsx`, `pages/settings/ConnectionsSettings.tsx`,
`components/settings/{SettingsSection,ProviderCard,ModelSelect,CapMeter,Field}.tsx`,
`components/ui/Toggle.tsx`, plus their Vitest tests.

**Modified:** `router.tsx` (nest settings routes), `hooks/useProviderConfigs.ts`
(broaden invalidation), `pages/BackupsPage.tsx` + `pages/ExportPage.tsx`
(restyle), `__tests__/Settings.test.tsx` + `__tests__/App.test.tsx` (new layout),
`e2e/pages/settings.py` (scope Save button per provider card; keep
`get_by_label("<provider> API key")` working).

**Removed:** `pages/Settings.tsx`, `components/ProviderConfigCard.tsx`,
`components/SchwabConnectionCard.tsx`, and their unit tests
(`__tests__/ProviderConfigCard.test.tsx`, `__tests__/SchwabConnectionCard.test.tsx`)
— replaced by the new component tests.

## Testing

- **Vitest/RTL:** `ProviderCard` (labeled fields render; `api_key_write` omitted
  when blank — regression test for the bug; toggle persists immediately; Save
  shows pending and pushes a success toast; invalid cap disables Save);
  `ConnectionsSettings` (connected vs. not-connected); `Toggle` (keyboard +
  `aria-checked`); rewritten `Settings.test.tsx` (rail links + AI Providers
  heading render through the layout). Backups/Export tests kept green (selectors
  updated only if necessary).
- **E2E:** preserve the selectors enumerated above. **Visual baselines must be
  regenerated** for `settings_general`, `settings_backups`, `settings_export`
  (`e2e/visual/test_route_snapshots.py`) via `make e2e-visual-update` — the
  baselines are root-owned, so regenerate in-container and inspect the diff.
- `make check` gates everything before commit.

## Risks & rollout

- **Visual snapshot churn** is expected and intentional; regenerate baselines as
  a discrete, reviewed step.
- **Multiple "Save" buttons** (one per provider) make the bare
  `get_by_role("button", name="Save")` ambiguous. This is pre-existing (the old
  card also rendered three). The page object will be updated to scope Save within
  a `data-testid="provider-card-{provider}"` wrapper.
- Retiring the old components requires updating every importer; all importers are
  enumerated under "Files" (router + four test files).
```
