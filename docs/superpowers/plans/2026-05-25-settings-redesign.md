# Settings Hub Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `/settings` into a Ledger-styled hub with a left sub-nav rail and nested routes (AI Providers, Connections, Backups, Export), fixing the UX (labeled fields, model dropdown, save feedback, enable toggle, cap meters) and the api-key-clearing bug.

**Architecture:** A `SettingsLayout` route renders a page header + vertical sub-nav rail + `<Outlet/>`; the four sections are child routes. Small reusable primitives (`Toggle`, `Field`, `SettingsSection`, `CapMeter`, `ModelSelect`) compose into `ProviderCard` and the section pages. No backend changes; reuses existing hooks and design tokens.

**Tech Stack:** React 18 + TypeScript, react-router-dom, @tanstack/react-query, Tailwind v4 with the in-repo "Ledger" tokens (`frontend/src/styles/globals.css`), Vitest + @testing-library/react. Everything runs in Docker.

**Spec:** `docs/superpowers/specs/2026-05-25-settings-redesign-design.md`

---

## Conventions for every task

- **Prerequisite:** dev stack up — `make dev` (first run builds images). All test/lint commands shell into containers.
- **Run one frontend test file:** `docker compose exec -T frontend pnpm exec vitest run src/__tests__/<File>.test.tsx`
- **Run one test by name:** append `-t "partial name"`.
- **Lint:** `docker compose exec -T frontend pnpm run lint`
- **Commit hook note:** if the lefthook pre-commit fails with container-relative path errors (known issue), re-run the same commit with `LEFTHOOK=0` prefixed. `make check` is the real gate.
- **Commit trailer:** every commit message ends with
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`
- Work happens on branch `feature/settings-redesign` (already created off `origin/main`).

## File map

**Create**
- `frontend/src/components/ui/Toggle.tsx` — accessible switch
- `frontend/src/components/settings/Field.tsx` — labeled field wrapper (render-prop)
- `frontend/src/components/settings/SettingsSection.tsx` — section header + body
- `frontend/src/components/settings/CapMeter.tsx` — single spend-vs-cap bar
- `frontend/src/components/settings/ModelSelect.tsx` — catalog dropdown + custom input
- `frontend/src/components/settings/ProviderCard.tsx` — one provider's config + save lifecycle
- `frontend/src/pages/settings/SettingsLayout.tsx` — hub shell (header + rail + Outlet)
- `frontend/src/pages/settings/ProvidersSettings.tsx` — three ProviderCards
- `frontend/src/pages/settings/ConnectionsSettings.tsx` — Schwab card
- Tests: `__tests__/Toggle.test.tsx`, `__tests__/Field.test.tsx`, `__tests__/SettingsSection.test.tsx`, `__tests__/CapMeter.test.tsx`, `__tests__/ModelSelect.test.tsx`, `__tests__/ProviderCard.test.tsx`, `__tests__/ConnectionsSettings.test.tsx`, `__tests__/SettingsLayout.test.tsx`

**Modify**
- `frontend/src/hooks/useProviderConfigs.ts` — broaden invalidation
- `frontend/src/router.tsx` — nest settings routes
- `frontend/src/pages/BackupsPage.tsx` — restyle to Ledger, fit under layout
- `frontend/src/pages/ExportPage.tsx` — restyle to Ledger, fit under layout
- `frontend/src/__tests__/App.test.tsx` — import SettingsLayout instead of Settings
- `e2e/pages/settings.py` — scope Save button per provider card

**Remove**
- `frontend/src/pages/Settings.tsx`
- `frontend/src/components/ProviderConfigCard.tsx`
- `frontend/src/components/SchwabConnectionCard.tsx`
- `frontend/src/__tests__/ProviderConfigCard.test.tsx`
- `frontend/src/__tests__/SchwabConnectionCard.test.tsx`
- `frontend/src/__tests__/Settings.test.tsx`

---

## Task 1: Toggle switch primitive

**Files:**
- Create: `frontend/src/components/ui/Toggle.tsx`
- Test: `frontend/src/__tests__/Toggle.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/Toggle.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import Toggle from "@/components/ui/Toggle";

describe("Toggle", () => {
  it("renders a switch reflecting checked state", () => {
    render(<Toggle checked label="Enable thing" onChange={() => {}} />);
    const sw = screen.getByRole("switch", { name: "Enable thing" });
    expect(sw).toHaveAttribute("aria-checked", "true");
  });

  it("calls onChange with the negated value on click", async () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} label="Enable thing" onChange={onChange} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("is operable by keyboard (Space)", async () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} label="Enable thing" onChange={onChange} />);
    screen.getByRole("switch").focus();
    await userEvent.keyboard(" ");
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("does not fire when disabled", async () => {
    const onChange = vi.fn();
    render(<Toggle checked={false} label="Enable thing" disabled onChange={onChange} />);
    await userEvent.click(screen.getByRole("switch"));
    expect(onChange).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/Toggle.test.tsx`
Expected: FAIL — cannot resolve `@/components/ui/Toggle`.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/ui/Toggle.tsx
type ToggleProps = {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
  id?: string;
};

export default function Toggle({ checked, onChange, label, disabled, id }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={[
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full border transition-colors",
        "border-rule disabled:opacity-50",
        checked ? "bg-copper-600" : "bg-ink-700",
      ].join(" ")}
    >
      <span
        aria-hidden
        className={[
          "inline-block h-3.5 w-3.5 transform rounded-full bg-ink-50 transition-transform duration-150 ease-ledger",
          checked ? "translate-x-[18px]" : "translate-x-[3px]",
        ].join(" ")}
      />
    </button>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/Toggle.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/Toggle.tsx frontend/src/__tests__/Toggle.test.tsx
git commit -m "feat(frontend): add accessible Toggle switch primitive

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Field labeled-input wrapper

**Files:**
- Create: `frontend/src/components/settings/Field.tsx`
- Test: `frontend/src/__tests__/Field.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/Field.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Field from "@/components/settings/Field";

describe("Field", () => {
  it("associates the label with the control via htmlFor/id", () => {
    render(
      <Field label="Daily cap">
        {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} />}
      </Field>,
    );
    // getByLabelText resolves only if label/control are wired correctly
    expect(screen.getByLabelText("Daily cap")).toBeInTheDocument();
  });

  it("renders a hint and wires aria-describedby to it", () => {
    render(
      <Field label="Daily cap" hint="Hard stop.">
        {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} />}
      </Field>,
    );
    const input = screen.getByLabelText("Daily cap");
    const hint = screen.getByText("Hard stop.");
    expect(input.getAttribute("aria-describedby")).toContain(hint.id);
  });

  it("shows the error instead of the hint when present", () => {
    render(
      <Field label="Daily cap" hint="Hard stop." error="Bad value">
        {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} />}
      </Field>,
    );
    expect(screen.getByText("Bad value")).toBeInTheDocument();
    expect(screen.queryByText("Hard stop.")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/Field.test.tsx`
Expected: FAIL — cannot resolve `@/components/settings/Field`.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/Field.tsx
import { useId } from "react";
import type { ReactNode } from "react";

type FieldProps = {
  label: string;
  hint?: string;
  error?: string;
  children: (props: { id: string; describedBy?: string }) => ReactNode;
};

export default function Field({ label, hint, error, children }: FieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errId = error ? `${id}-err` : undefined;
  const describedBy = [error ? errId : hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={id}
        className="block font-mono text-[10px] uppercase tracking-loose2 text-copper-400"
      >
        {label}
      </label>
      {children({ id, describedBy })}
      {hint && !error && <p id={hintId} className="text-[11px] text-ink-400">{hint}</p>}
      {error && <p id={errId} className="text-[11px] text-loss">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/Field.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/Field.tsx frontend/src/__tests__/Field.test.tsx
git commit -m "feat(frontend): add Field labeled-input wrapper for settings

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: SettingsSection header

**Files:**
- Create: `frontend/src/components/settings/SettingsSection.tsx`
- Test: `frontend/src/__tests__/SettingsSection.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/SettingsSection.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import SettingsSection from "@/components/settings/SettingsSection";

describe("SettingsSection", () => {
  it("renders a heading with the title and the children", () => {
    render(
      <SettingsSection title="AI Providers" description="Keys and caps.">
        <div>body content</div>
      </SettingsSection>,
    );
    expect(screen.getByRole("heading", { name: "AI Providers" })).toBeInTheDocument();
    expect(screen.getByText("Keys and caps.")).toBeInTheDocument();
    expect(screen.getByText("body content")).toBeInTheDocument();
  });

  it("renders an optional header action", () => {
    render(
      <SettingsSection title="Backups" action={<button>Back up now</button>}>
        <div />
      </SettingsSection>,
    );
    expect(screen.getByRole("button", { name: "Back up now" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/SettingsSection.test.tsx`
Expected: FAIL — cannot resolve module.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/SettingsSection.tsx
import type { ReactNode } from "react";

type Props = {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
};

export default function SettingsSection({ title, description, action, children }: Props) {
  return (
    <section className="ledger-fade-in">
      <header className="mb-5 flex items-end justify-between gap-4">
        <div>
          <h2 className="font-display text-[1.2rem] text-ink-50 tracking-tight2">{title}</h2>
          {description && <p className="mt-1 text-[13px] text-ink-300">{description}</p>}
        </div>
        {action}
      </header>
      <div className="space-y-4">{children}</div>
    </section>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/SettingsSection.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/SettingsSection.tsx frontend/src/__tests__/SettingsSection.test.tsx
git commit -m "feat(frontend): add SettingsSection header component

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: CapMeter bar

**Files:**
- Create: `frontend/src/components/settings/CapMeter.tsx`
- Test: `frontend/src/__tests__/CapMeter.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/CapMeter.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CapMeter from "@/components/settings/CapMeter";

describe("CapMeter", () => {
  it("shows spent / cap and a rounded percentage", () => {
    render(<CapMeter label="Daily" cap="10.00" spent="6.00" pct={0.6} />);
    expect(screen.getByText("Daily")).toBeInTheDocument();
    expect(screen.getByText("$6.00 / $10.00")).toBeInTheDocument();
    expect(screen.getByText("60%")).toBeInTheDocument();
  });

  it("caps the bar width at 100% when over budget", () => {
    render(<CapMeter label="Daily" cap="10.00" spent="25.00" pct={2.5} />);
    const fill = screen.getByTestId("capmeter-fill");
    expect(fill).toHaveStyle({ width: "100%" });
    expect(screen.getByText("250%")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/CapMeter.test.tsx`
Expected: FAIL — cannot resolve module.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/CapMeter.tsx
function barGradient(pct: number): string {
  if (pct >= 1.0) return "linear-gradient(90deg, var(--loss-500) 0%, var(--loss-400) 100%)";
  if (pct >= 0.8) return "linear-gradient(90deg, var(--copper-500) 0%, var(--copper-300) 100%)";
  return "linear-gradient(90deg, var(--gain-500) 0%, var(--gain-400) 100%)";
}
function toneClass(pct: number): string {
  if (pct >= 1.0) return "text-loss";
  if (pct >= 0.8) return "text-copper-300";
  return "text-gain";
}

type Props = { label: string; cap: string; spent: string; pct: number };

export default function CapMeter({ label, cap, spent, pct }: Props) {
  return (
    <div className="grid grid-cols-[64px_1fr_auto_44px] items-center gap-3 text-[12px]">
      <span className="font-mono text-[10px] uppercase tracking-wider text-ink-400">{label}</span>
      <div className="relative h-[6px] bg-ink-void rounded-sm overflow-hidden border border-rule">
        <div
          data-testid="capmeter-fill"
          className="h-full transition-[width] duration-700 ease-ledger"
          style={{ width: `${Math.min(100, pct * 100)}%`, background: barGradient(pct) }}
        />
      </div>
      <span className="font-mono tabular-nums text-ink-200">{`$${spent} / $${cap}`}</span>
      <span className={`font-mono tabular-nums text-right ${toneClass(pct)}`}>{`${Math.round(pct * 100)}%`}</span>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/CapMeter.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/CapMeter.tsx frontend/src/__tests__/CapMeter.test.tsx
git commit -m "feat(frontend): add CapMeter spend-vs-cap bar

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: ModelSelect (catalog dropdown + custom)

**Files:**
- Create: `frontend/src/components/settings/ModelSelect.tsx`
- Test: `frontend/src/__tests__/ModelSelect.test.tsx`

Reference: `useAiModels(provider)` (`@/hooks/useAiModels`) returns `{ data?: { models: AiModel[] } }`; `AiModel` has `{ id, name, provider, ... }` (`@/api/ai`).

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/ModelSelect.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ModelSelect from "@/components/settings/ModelSelect";

const mockUseAiModels = vi.fn();
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));

const claudeModels = {
  models: [
    { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6", provider: "claude",
      input_per_mtok: 3, output_per_mtok: 15, cached_per_mtok: 0.3, context_window: 200000, supports_vision: true },
    { id: "claude-opus-4-7", name: "Claude Opus 4.7", provider: "claude",
      input_per_mtok: 15, output_per_mtok: 75, cached_per_mtok: 1.5, context_window: 200000, supports_vision: true },
  ],
};

beforeEach(() => mockUseAiModels.mockReturnValue({ data: claudeModels }));

describe("ModelSelect", () => {
  it("lists catalog models for the provider", () => {
    render(<ModelSelect provider="claude" value="claude-sonnet-4-6" onChange={() => {}} />);
    expect(screen.getByRole("option", { name: "Claude Sonnet 4.6" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Claude Opus 4.7" })).toBeInTheDocument();
  });

  it("selecting a catalog model emits its id", async () => {
    const onChange = vi.fn();
    render(<ModelSelect provider="claude" value="claude-sonnet-4-6" onChange={onChange} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "claude-opus-4-7");
    expect(onChange).toHaveBeenCalledWith("claude-opus-4-7");
  });

  it("shows a custom text input when value is not in the catalog", () => {
    render(<ModelSelect provider="local" value="llama-3.1" onChange={() => {}} />);
    expect(screen.getByLabelText("Custom model id")).toHaveValue("llama-3.1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ModelSelect.test.tsx`
Expected: FAIL — cannot resolve module.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/components/settings/ModelSelect.tsx
import { useAiModels } from "@/hooks/useAiModels";
import type { AiModel } from "@/api/ai";

const CUSTOM = "__custom__";

type Props = {
  provider: string;
  value: string;
  onChange: (model: string) => void;
  id?: string;
  describedBy?: string;
};

export default function ModelSelect({ provider, value, onChange, id, describedBy }: Props) {
  const { data } = useAiModels(provider);
  const models: AiModel[] = (data?.models ?? []).filter((m) => m.provider === provider);
  const known = models.some((m) => m.id === value);
  const showCustom = !known;

  return (
    <div className="space-y-2">
      <select
        id={id}
        aria-describedby={describedBy}
        value={showCustom ? CUSTOM : value}
        onChange={(e) => onChange(e.target.value === CUSTOM ? "" : e.target.value)}
        className="ledger-input w-full py-2"
      >
        {models.map((m) => (
          <option key={m.id} value={m.id}>{m.name}</option>
        ))}
        <option value={CUSTOM}>Custom…</option>
      </select>
      {showCustom && (
        <input
          aria-label="Custom model id"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="e.g. llama-3.1-70b"
          className="ledger-input w-full py-2 font-mono text-[12px]"
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ModelSelect.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/ModelSelect.tsx frontend/src/__tests__/ModelSelect.test.tsx
git commit -m "feat(frontend): add ModelSelect catalog dropdown with custom fallback

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Broaden useUpsertProviderConfig invalidation

**Files:**
- Modify: `frontend/src/hooks/useProviderConfigs.ts`
- Test: `frontend/src/__tests__/hooks/useUpsertProviderConfig.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/hooks/useUpsertProviderConfig.test.tsx
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient } from "@tanstack/react-query";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useUpsertProviderConfig } from "@/hooks/useProviderConfigs";
import { hookWrapper, newQueryClient } from "../testUtils";

vi.mock("@/api/ai", () => ({
  upsertProviderConfig: vi.fn(async () => ({ provider: "claude" })),
}));

let qc: QueryClient;
beforeEach(() => { qc = newQueryClient(); });

describe("useUpsertProviderConfig", () => {
  it("invalidates provider-configs, ai-usage and costs-caps on success", async () => {
    const spy = vi.spyOn(qc, "invalidateQueries");
    const { result } = renderHook(() => useUpsertProviderConfig(), { wrapper: hookWrapper(qc) });
    result.current.mutate({ provider: "claude", body: { enabled: true } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const keys = spy.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(["provider-configs"]));
    expect(keys).toContain(JSON.stringify(["ai-usage"]));
    expect(keys).toContain(JSON.stringify(["costs-caps"]));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/hooks/useUpsertProviderConfig.test.tsx`
Expected: FAIL — only `["provider-configs"]` is invalidated today.

- [ ] **Step 3: Edit the hook**

Replace the body of `useUpsertProviderConfig` in `frontend/src/hooks/useProviderConfigs.ts` so `onSuccess` invalidates all three keys:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchProviderConfigs, upsertProviderConfig } from "@/api/ai";

export const useProviderConfigs = () =>
  useQuery({ queryKey: ["provider-configs"], queryFn: fetchProviderConfigs });

export function useUpsertProviderConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ provider, body }: { provider: string; body: Parameters<typeof upsertProviderConfig>[1] }) =>
      upsertProviderConfig(provider, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["provider-configs"] });
      qc.invalidateQueries({ queryKey: ["ai-usage"] });
      qc.invalidateQueries({ queryKey: ["costs-caps"] });
    },
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/hooks/useUpsertProviderConfig.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useProviderConfigs.ts frontend/src/__tests__/hooks/useUpsertProviderConfig.test.tsx
git commit -m "feat(frontend): refresh usage + caps after provider config save

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: ProviderCard — fields, masking, save round-trip + api-key-omit fix

**Files:**
- Create: `frontend/src/components/settings/ProviderCard.tsx`
- Test: `frontend/src/__tests__/ProviderCard.test.tsx`

This task builds the full `ProviderCard`. The enable-toggle, cap meters, and validation behaviors are exercised in Task 8 (same file, additional tests) — the implementation below already includes them so Task 8 adds only tests.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/ProviderCard.test.tsx
import { render, screen, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ProviderCard from "@/components/settings/ProviderCard";
import type { ProviderConfig } from "@/api/ai";

const mockMutate = vi.fn();
const mockUseProviderConfigs = vi.fn();
const mockUseAiUsage = vi.fn();
const mockUseCostsCaps = vi.fn();
const mockUseAiModels = vi.fn();
const mockPush = vi.fn();

vi.mock("@/hooks/useProviderConfigs", () => ({
  useProviderConfigs: () => mockUseProviderConfigs(),
  useUpsertProviderConfig: () => ({ mutate: mockMutate, isPending: false }),
}));
vi.mock("@/hooks/useAiUsage", () => ({ useAiUsage: () => mockUseAiUsage() }));
vi.mock("@/hooks/useCosts", () => ({ useCostsCaps: () => mockUseCostsCaps() }));
vi.mock("@/hooks/useAiModels", () => ({ useAiModels: () => mockUseAiModels() }));
vi.mock("@/hooks/useToast", () => ({ useToast: () => ({ push: mockPush }) }));

function cfg(o: Partial<ProviderConfig> = {}): ProviderConfig {
  return {
    provider: "claude", base_url: "", default_model: "claude-sonnet-4-6",
    enabled: true, supports_vision: true, daily_cost_cap_usd: "10.00",
    monthly_cost_cap_usd: null, api_key_present: true, ...o,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockUseProviderConfigs.mockReturnValue({ data: [cfg()] });
  mockUseAiUsage.mockReturnValue({ data: { today: { claude: "0.4231" } } });
  mockUseCostsCaps.mockReturnValue({ data: [] });
  mockUseAiModels.mockReturnValue({ data: { models: [
    { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6", provider: "claude",
      input_per_mtok: 3, output_per_mtok: 15, cached_per_mtok: 0.3, context_window: 200000, supports_vision: true },
  ] } });
});

describe("ProviderCard", () => {
  it("renders a labeled API key input named '<Provider> API key'", () => {
    render(<ProviderCard provider="claude" />);
    expect(screen.getByLabelText("Claude API key")).toBeInTheDocument();
  });

  it("shows a 'key set' indicator and today's spend", () => {
    render(<ProviderCard provider="claude" />);
    expect(screen.getByText(/key set/i)).toBeInTheDocument();
    expect(screen.getByText(/0\.4231/)).toBeInTheDocument();
  });

  it("omits api_key_write from the save body when the key field is untouched (bug fix)", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mockMutate).toHaveBeenCalledTimes(1);
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.provider).toBe("claude");
    expect("api_key_write" in arg.body).toBe(false);
  });

  it("includes api_key_write only when a new key was typed", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.type(screen.getByLabelText("Claude API key"), "sk-new");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg] = mockMutate.mock.calls[0];
    expect(arg.body.api_key_write).toBe("sk-new");
  });

  it("sends monthly cap as null when blank and clears the draft on success", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.type(screen.getByLabelText("Claude API key"), "sk-temp");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const [arg, opts] = mockMutate.mock.calls[0];
    expect(arg.body.monthly_cost_cap_usd).toBeNull();
    await act(async () => { opts.onSuccess(); });
    expect(screen.getByLabelText("Claude API key")).toHaveValue("");
    expect(mockPush).toHaveBeenCalledWith(expect.objectContaining({ kind: "success" }));
  });

  it("renders the base URL field only for the local provider", () => {
    mockUseProviderConfigs.mockReturnValue({ data: [cfg({ provider: "local", api_key_present: false })] });
    render(<ProviderCard provider="local" />);
    expect(screen.getByLabelText("Base URL")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ProviderCard.test.tsx`
Expected: FAIL — cannot resolve `@/components/settings/ProviderCard`.

- [ ] **Step 3: Write the implementation**

```tsx
// frontend/src/components/settings/ProviderCard.tsx
import { useState } from "react";
import { useProviderConfigs, useUpsertProviderConfig } from "@/hooks/useProviderConfigs";
import { useAiUsage } from "@/hooks/useAiUsage";
import { useCostsCaps } from "@/hooks/useCosts";
import { useToast } from "@/hooks/useToast";
import type { ProviderConfig } from "@/api/ai";
import Field from "@/components/settings/Field";
import Toggle from "@/components/ui/Toggle";
import ModelSelect from "@/components/settings/ModelSelect";
import CapMeter from "@/components/settings/CapMeter";

type ProviderId = "claude" | "openai" | "local";
const LABEL: Record<ProviderId, string> = { claude: "Claude", openai: "OpenAI", local: "Local" };
const DEFAULT_MODEL: Record<ProviderId, string> = {
  claude: "claude-sonnet-4-6", openai: "gpt-5", local: "",
};

type Draft = {
  api_key_write?: string;
  default_model?: string;
  daily_cost_cap_usd?: string;
  monthly_cost_cap_usd?: string;
  base_url?: string;
};

export default function ProviderCard({ provider }: { provider: ProviderId }) {
  const { data: configs } = useProviderConfigs();
  const { data: usage } = useAiUsage();
  const { data: caps } = useCostsCaps();
  const upsert = useUpsertProviderConfig();
  const { push } = useToast();
  const [draft, setDraft] = useState<Draft>({});

  const cfg = configs?.find((c) => c.provider === provider);
  const capRow = caps?.find((r) => r.provider === provider);
  const spent = usage?.today?.[provider] ?? "0";
  const enabled = cfg?.enabled ?? true;

  const model = draft.default_model ?? cfg?.default_model ?? DEFAULT_MODEL[provider];
  const daily = draft.daily_cost_cap_usd ?? cfg?.daily_cost_cap_usd ?? "10.00";
  const monthly = draft.monthly_cost_cap_usd ?? cfg?.monthly_cost_cap_usd ?? "";
  const baseUrl = draft.base_url ?? cfg?.base_url ?? "";
  const apiKey = draft.api_key_write ?? "";

  const dailyNum = Number(daily);
  const monthlyNum = monthly === "" ? null : Number(monthly);
  const dailyInvalid = daily.trim() === "" || Number.isNaN(dailyNum) || dailyNum < 0;
  const monthlyInvalid = monthly !== "" && (Number.isNaN(monthlyNum as number) || (monthlyNum as number) < 0);
  const modelInvalid = model.trim() === "";
  const invalid = dailyInvalid || monthlyInvalid || modelInvalid;

  const set = (patch: Draft) => setDraft((d) => ({ ...d, ...patch }));

  const toggleEnabled = (next: boolean) => {
    upsert.mutate(
      { provider, body: { enabled: next } },
      {
        onSuccess: () => push({ kind: "info", text: `${LABEL[provider]} ${next ? "enabled" : "disabled"}.` }),
        onError: (e) => push({ kind: "error", text: (e as Error).message }),
      },
    );
  };

  const save = () => {
    if (invalid) return;
    const body: Partial<ProviderConfig> & { api_key_write?: string } = {
      default_model: model,
      daily_cost_cap_usd: daily,
      monthly_cost_cap_usd: monthly === "" ? null : monthly,
      base_url: baseUrl,
    };
    if (apiKey) body.api_key_write = apiKey; // omit when blank → serializer keeps the stored key
    upsert.mutate(
      { provider, body },
      {
        onSuccess: () => { setDraft({}); push({ kind: "success", text: `${LABEL[provider]} settings saved.` }); },
        onError: (e) => push({ kind: "error", text: (e as Error).message }),
      },
    );
  };

  return (
    <div className="ledger-surface p-5" data-testid={`provider-card-${provider}`}>
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className={`inline-block h-2 w-2 rounded-full ${enabled ? "bg-copper-400" : "bg-ink-600"}`} aria-hidden />
          <h3 className="font-display text-[1.05rem] text-ink-50">{LABEL[provider]}</h3>
          <span className="ledger-pill" data-tone={cfg?.api_key_present ? "copper" : undefined}>
            {cfg?.api_key_present ? "key set ••••" : "no key"}
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span className="font-mono text-[11px] text-ink-400 tabular-nums">today ${Number(spent).toFixed(4)}</span>
          <Toggle checked={enabled} onChange={toggleEnabled} label={`${LABEL[provider]} enabled`} disabled={upsert.isPending} />
        </div>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field
            label={`${LABEL[provider]} API key`}
            hint={cfg?.api_key_present ? "A key is stored. Paste to replace; leave blank to keep." : "Paste your API key."}
          >
            {({ id, describedBy }) => (
              <input
                id={id} aria-describedby={describedBy} type="password" value={apiKey}
                placeholder={cfg?.api_key_present ? "•••••••• (unchanged)" : "sk-…"}
                onChange={(e) => set({ api_key_write: e.target.value })}
                className="ledger-input w-full py-2 font-mono text-[12px]"
              />
            )}
          </Field>
        </div>

        <Field label="Default model" error={modelInvalid ? "Pick or enter a model." : undefined}>
          {({ id, describedBy }) => (
            <ModelSelect provider={provider} value={model} id={id} describedBy={describedBy}
              onChange={(m) => set({ default_model: m })} />
          )}
        </Field>

        {provider === "local" && (
          <Field label="Base URL" hint="OpenAI-compatible endpoint.">
            {({ id, describedBy }) => (
              <input
                id={id} aria-describedby={describedBy} value={baseUrl}
                placeholder="http://host.docker.internal:11434/v1"
                onChange={(e) => set({ base_url: e.target.value })}
                className="ledger-input w-full py-2 font-mono text-[12px]"
              />
            )}
          </Field>
        )}

        <Field label="Daily cap (USD)" hint="Hard stop — runs blocked past this."
               error={dailyInvalid ? "Enter a non-negative number." : undefined}>
          {({ id, describedBy }) => (
            <input id={id} aria-describedby={describedBy} inputMode="decimal" value={daily}
              onChange={(e) => set({ daily_cost_cap_usd: e.target.value })}
              className="ledger-input w-full py-2 tabular-nums" />
          )}
        </Field>

        <Field label="Monthly cap (USD)" hint="Blank = no monthly limit."
               error={monthlyInvalid ? "Enter a non-negative number or leave blank." : undefined}>
          {({ id, describedBy }) => (
            <input id={id} aria-describedby={describedBy} inputMode="decimal" value={monthly} placeholder="none"
              onChange={(e) => set({ monthly_cost_cap_usd: e.target.value })}
              className="ledger-input w-full py-2 tabular-nums" />
          )}
        </Field>
      </div>

      {capRow && (
        <div className="mt-5 space-y-2 border-t border-rule-soft pt-4">
          <CapMeter label="Daily" cap={capRow.daily.cap} spent={capRow.daily.spent} pct={capRow.daily.pct} />
          {capRow.monthly && (
            <CapMeter label="Monthly" cap={capRow.monthly.cap} spent={capRow.monthly.spent} pct={capRow.monthly.pct} />
          )}
        </div>
      )}

      <div className="mt-5">
        <button type="button" className="ledger-cta" onClick={save} disabled={upsert.isPending || invalid}>
          {upsert.isPending ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ProviderCard.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/settings/ProviderCard.tsx frontend/src/__tests__/ProviderCard.test.tsx
git commit -m "feat(frontend): add ProviderCard with labeled fields and api-key-omit fix

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: ProviderCard — enable toggle, cap meters, validation (add tests)

**Files:**
- Modify: `frontend/src/__tests__/ProviderCard.test.tsx` (append a describe block)
- (No implementation change — Task 7 already implements these.)

- [ ] **Step 1: Append the failing tests**

Add this block at the end of `frontend/src/__tests__/ProviderCard.test.tsx`:

```tsx
describe("ProviderCard — toggle, meters, validation", () => {
  it("persists the enable toggle immediately", async () => {
    render(<ProviderCard provider="claude" />);
    await userEvent.click(screen.getByRole("switch", { name: "Claude enabled" }));
    expect(mockMutate).toHaveBeenCalledWith(
      { provider: "claude", body: { enabled: false } },
      expect.any(Object),
    );
  });

  it("renders daily and monthly cap meters from costs-caps", () => {
    mockUseCostsCaps.mockReturnValue({ data: [
      { provider: "claude", daily: { cap: "10.00", spent: "6.00", pct: 0.6 },
        monthly: { cap: "100.00", spent: "20.00", pct: 0.2 } },
    ] });
    render(<ProviderCard provider="claude" />);
    expect(screen.getByText("$6.00 / $10.00")).toBeInTheDocument();
    expect(screen.getByText("$20.00 / $100.00")).toBeInTheDocument();
  });

  it("disables Save when the daily cap is invalid", async () => {
    render(<ProviderCard provider="claude" />);
    const daily = screen.getByLabelText("Daily cap (USD)");
    await userEvent.clear(daily);
    await userEvent.type(daily, "-5");
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run to verify the new tests pass (implementation already exists)**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ProviderCard.test.tsx`
Expected: PASS (9 tests total). If the toggle or validation test fails, fix `ProviderCard.tsx` to match (do not weaken the test).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/ProviderCard.test.tsx
git commit -m "test(frontend): cover ProviderCard toggle, cap meters, validation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: ProvidersSettings page

**Files:**
- Create: `frontend/src/pages/settings/ProvidersSettings.tsx`
- Test: `frontend/src/__tests__/ProvidersSettings.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/ProvidersSettings.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ProvidersSettings from "@/pages/settings/ProvidersSettings";

// ProviderCard is unit-tested separately; stub it to keep this test focused.
vi.mock("@/components/settings/ProviderCard", () => ({
  default: ({ provider }: { provider: string }) => <div data-testid={`pc-${provider}`} />,
}));

describe("ProvidersSettings", () => {
  it("renders a card for claude, openai and local under an AI Providers heading", () => {
    render(<ProvidersSettings />);
    expect(screen.getByRole("heading", { name: "AI Providers" })).toBeInTheDocument();
    expect(screen.getByTestId("pc-claude")).toBeInTheDocument();
    expect(screen.getByTestId("pc-openai")).toBeInTheDocument();
    expect(screen.getByTestId("pc-local")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ProvidersSettings.test.tsx`
Expected: FAIL — cannot resolve module.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/pages/settings/ProvidersSettings.tsx
import SettingsSection from "@/components/settings/SettingsSection";
import ProviderCard from "@/components/settings/ProviderCard";

const PROVIDERS = ["claude", "openai", "local"] as const;

export default function ProvidersSettings() {
  return (
    <SettingsSection title="AI Providers" description="Keys, default models, and spend caps per provider.">
      {PROVIDERS.map((p) => <ProviderCard key={p} provider={p} />)}
    </SettingsSection>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ProvidersSettings.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/settings/ProvidersSettings.tsx frontend/src/__tests__/ProvidersSettings.test.tsx
git commit -m "feat(frontend): add ProvidersSettings section page

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: ConnectionsSettings page

**Files:**
- Create: `frontend/src/pages/settings/ConnectionsSettings.tsx`
- Test: `frontend/src/__tests__/ConnectionsSettings.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/ConnectionsSettings.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ConnectionsSettings from "@/pages/settings/ConnectionsSettings";

const mockUseSchwabStatus = vi.fn();
vi.mock("@/hooks/useSchwabStatus", () => ({ useSchwabStatus: () => mockUseSchwabStatus() }));
vi.mock("@/api/schwab", () => ({ fetchSchwabAuthorizeUrl: vi.fn(async () => ({ url: "/x" })) }));

beforeEach(() => vi.clearAllMocks());

describe("ConnectionsSettings", () => {
  it("shows not-connected state with a Connect button", () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: false }, isLoading: false });
    render(<ConnectionsSettings />);
    expect(screen.getByText(/not connected/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /connect schwab/i })).toBeInTheDocument();
  });

  it("shows connected state with a Reconnect button", () => {
    mockUseSchwabStatus.mockReturnValue({ data: { connected: true, expires_at: null }, isLoading: false });
    render(<ConnectionsSettings />);
    expect(screen.getByText(/^connected$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reconnect/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ConnectionsSettings.test.tsx`
Expected: FAIL — cannot resolve module.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/pages/settings/ConnectionsSettings.tsx
import { useSchwabStatus } from "@/hooks/useSchwabStatus";
import { fetchSchwabAuthorizeUrl } from "@/api/schwab";
import { formatDistanceToNow } from "date-fns";
import SettingsSection from "@/components/settings/SettingsSection";

export default function ConnectionsSettings() {
  const { data, isLoading } = useSchwabStatus();
  const connected = data?.connected ?? false;

  const onConnect = async () => {
    const { url } = await fetchSchwabAuthorizeUrl();
    window.location.href = url;
  };

  return (
    <SettingsSection title="Connections" description="Market-data and brokerage links.">
      <div className="ledger-surface p-5" data-testid="schwab-card">
        <div className="flex items-center gap-3">
          <h3 className="font-display text-[1.05rem] text-ink-50">Charles Schwab</h3>
          {!isLoading && (
            <span className="ledger-pill" data-tone={connected ? "gain" : "loss"}>
              {connected ? "Connected" : "Not connected"}
            </span>
          )}
        </div>
        <p className="mt-2 text-[13px] text-ink-300">
          Powers live quotes, OHLC history, option chains, and positions.
        </p>
        {isLoading ? (
          <p className="mt-3 text-ink-400 text-sm">Checking…</p>
        ) : (
          <>
            {connected && data?.expires_at && (
              <p className="mt-2 font-mono text-[11px] text-ink-400">
                token refreshes in {formatDistanceToNow(new Date(data.expires_at))}
              </p>
            )}
            <button type="button" onClick={onConnect} className="ledger-cta mt-4">
              {connected ? "Reconnect" : "Connect Schwab"}
            </button>
          </>
        )}
      </div>
    </SettingsSection>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ConnectionsSettings.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/settings/ConnectionsSettings.tsx frontend/src/__tests__/ConnectionsSettings.test.tsx
git commit -m "feat(frontend): add ConnectionsSettings (Schwab) section page

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: SettingsLayout (header + sub-nav rail + Outlet)

**Files:**
- Create: `frontend/src/pages/settings/SettingsLayout.tsx`
- Test: `frontend/src/__tests__/SettingsLayout.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/SettingsLayout.test.tsx
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect } from "vitest";
import SettingsLayout from "@/pages/settings/SettingsLayout";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/settings" element={<SettingsLayout />}>
          <Route index element={<div>providers-outlet</div>} />
          <Route path="connections" element={<div>connections-outlet</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("SettingsLayout", () => {
  it("renders the rail links and the page title", () => {
    renderAt("/settings");
    const nav = screen.getByRole("navigation", { name: /settings sections/i });
    ["AI Providers", "Connections", "Backups", "Export"].forEach((label) => {
      expect(within(nav).getByRole("link", { name: label })).toBeInTheDocument();
    });
    expect(screen.getByText(/Ledger · Settings/i)).toBeInTheDocument();
  });

  it("renders the matched child route via Outlet", () => {
    renderAt("/settings");
    expect(screen.getByText("providers-outlet")).toBeInTheDocument();
    renderAt("/settings/connections");
    expect(screen.getByText("connections-outlet")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/SettingsLayout.test.tsx`
Expected: FAIL — cannot resolve module.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/pages/settings/SettingsLayout.tsx
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/SettingsLayout.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/settings/SettingsLayout.tsx frontend/src/__tests__/SettingsLayout.test.tsx
git commit -m "feat(frontend): add SettingsLayout hub shell with sub-nav rail

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Wire the router & retire the old Settings trio

**Files:**
- Modify: `frontend/src/router.tsx`
- Modify: `frontend/src/__tests__/App.test.tsx`
- Remove: `frontend/src/pages/Settings.tsx`, `frontend/src/components/ProviderConfigCard.tsx`, `frontend/src/components/SchwabConnectionCard.tsx`, `frontend/src/__tests__/ProviderConfigCard.test.tsx`, `frontend/src/__tests__/SchwabConnectionCard.test.tsx`, `frontend/src/__tests__/Settings.test.tsx`

- [ ] **Step 1: Update `App.test.tsx`** so it no longer imports the deleted page

Replace line 5 `import Settings from "../pages/Settings";` with:

```tsx
import SettingsLayout from "../pages/settings/SettingsLayout";
```

Replace the "renders Settings heading" test body (lines 14-17) with:

```tsx
  it("renders Settings hub heading", () => {
    renderWithProviders(<SettingsLayout />, { client: queryClient });
    expect(screen.getByText(/Ledger · Settings/i)).toBeInTheDocument();
  });
```

- [ ] **Step 2: Edit `router.tsx`**

Remove the import on line 4 (`import Settings from "./pages/Settings";`) and add three imports near the other page imports:

```tsx
import SettingsLayout from "./pages/settings/SettingsLayout";
import ProvidersSettings from "./pages/settings/ProvidersSettings";
import ConnectionsSettings from "./pages/settings/ConnectionsSettings";
```

Replace the single settings route (`{ path: "settings", element: <Settings />, handle: { crumb: "Settings" } },`) with the nested layout route:

```tsx
      {
        path: "settings",
        element: <SettingsLayout />,
        handle: { crumb: "Settings" },
        children: [
          { index: true, element: <ProvidersSettings />, handle: { crumb: "AI Providers" } },
          { path: "connections", element: <ConnectionsSettings />, handle: { crumb: "Connections" } },
          { path: "backups", element: <BackupsPage />, handle: { crumb: "Backups" } },
          { path: "export", element: <ExportPage />, handle: { crumb: "Export" } },
        ],
      },
```

Then DELETE the now-duplicate flat routes:

```tsx
      { path: "settings/backups", element: <BackupsPage />, handle: { crumb: "Backups" } },
      { path: "settings/export", element: <ExportPage />, handle: { crumb: "Export" } },
```

(Keep the existing `import BackupsPage` and `import ExportPage` lines.)

- [ ] **Step 3: Delete the retired files**

```bash
git rm frontend/src/pages/Settings.tsx \
       frontend/src/components/ProviderConfigCard.tsx \
       frontend/src/components/SchwabConnectionCard.tsx \
       frontend/src/__tests__/ProviderConfigCard.test.tsx \
       frontend/src/__tests__/SchwabConnectionCard.test.tsx \
       frontend/src/__tests__/Settings.test.tsx
```

- [ ] **Step 4: Verify nothing else references the removed modules**

Run: `grep -rn "ProviderConfigCard\|SchwabConnectionCard\|pages/Settings\b" frontend/src`
Expected: no matches. If any remain, update them.

- [ ] **Step 5: Run the affected suites + typecheck via lint**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/App.test.tsx`
Expected: PASS.
Run: `docker compose exec -T frontend pnpm run lint`
Expected: PASS (no unused imports, no broken references).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/router.tsx frontend/src/__tests__/App.test.tsx
git commit -m "feat(frontend): nest settings routes under SettingsLayout; retire old cards

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Restyle BackupsPage to Ledger, fit under layout

**Files:**
- Modify: `frontend/src/pages/BackupsPage.tsx`
- Test: `frontend/src/__tests__/BackupsPage.test.tsx` (existing — must stay green)

**Contract to preserve** (existing test + `e2e/pages/backups.py`): a button whose name matches `/back up now/i`; rows with `data-testid="backup-row-{id}"`; a "Download" link and "Delete" button per `ok` row; the filename text rendered as-is. Do **not** wrap in a second `<main>` (it renders inside `SettingsLayout`'s `<main>`).

- [ ] **Step 1: Run the existing test first (baseline green)**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/BackupsPage.test.tsx`
Expected: PASS (2 tests) before any change.

- [ ] **Step 2: Replace the file contents**

```tsx
// frontend/src/pages/BackupsPage.tsx
import { useState } from "react";
import { useBackups, useDeleteBackup, useRunBackupNow } from "@/hooks/useBackups";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/useToast";
import SettingsSection from "@/components/settings/SettingsSection";

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function BackupsPage() {
  const { data = [], isLoading } = useBackups();
  const { push } = useToast();
  const run = useRunBackupNow();
  const del = useDeleteBackup();
  const [confirm, setConfirm] = useState<number | null>(null);

  return (
    <SettingsSection
      title="Backups"
      description="Daily at 02:30 UTC · keep last 7 scheduled."
      action={
        <button
          className="ledger-cta disabled:opacity-50"
          disabled={run.isPending}
          onClick={() => run.mutate(undefined, {
            onSuccess: () => push({ kind: "info", text: "Backup queued." }),
            onError: (e) => push({ kind: "error", text: (e as Error).message }),
          })}
        >
          {run.isPending ? "Queuing…" : "Back up now"}
        </button>
      }
    >
      {isLoading && <SkeletonRows rows={4} />}
      {!isLoading && data.length === 0 && (
        <EmptyState title="No backups yet" body="The nightly job will create one at 02:30 UTC." />
      )}

      {data.length > 0 && (
        <div className="ledger-surface overflow-hidden">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-rule text-left">
                {["Created", "Filename", "Size", "Kind", "Status", ""].map((h, i) => (
                  <th key={i} className="px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-copper-400">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-rule-soft">
              {data.map((b) => (
                <tr key={b.id} data-testid={`backup-row-${b.id}`} className={b.status !== "ok" ? "opacity-60" : ""}>
                  <td className="px-4 py-2.5 text-ink-300">{new Date(b.created_at).toLocaleString()}</td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-ink-200">{b.filename}</td>
                  <td className="px-4 py-2.5 tabular-nums text-ink-200">{fmtSize(b.size_bytes)}</td>
                  <td className="px-4 py-2.5">
                    <span className="ledger-pill">{b.kind}</span>
                  </td>
                  <td className="px-4 py-2.5">
                    {b.status === "failed"
                      ? <span title={b.error} className="text-loss">✗ failed</span>
                      : <span className="text-gain">{b.status}</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right whitespace-nowrap">
                    {b.status === "ok" && (
                      <>
                        <a className="text-copper-300 hover:text-copper-200 text-[12px] mr-4"
                           href={`/api/backups/${b.id}/download/`}>Download</a>
                        <button className="text-loss hover:underline text-[12px]"
                                onClick={() => setConfirm(b.id)}>Delete</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirm !== null && (
        <div role="dialog" aria-modal="true" aria-label="Confirm delete backup"
             className="fixed inset-0 bg-black/70 grid place-items-center z-50"
             onClick={() => setConfirm(null)}>
          <div className="ledger-surface p-5 w-96" tabIndex={-1} onClick={(e) => e.stopPropagation()}>
            <p className="text-ink-200">Delete this backup? The file on disk will be removed.</p>
            <div className="flex justify-end gap-2 mt-4">
              <button className="ledger-ghost" onClick={() => setConfirm(null)}>Cancel</button>
              <button
                className="ledger-cta"
                style={{ background: "linear-gradient(180deg, var(--loss-400), var(--loss-500))", borderColor: "var(--loss-500)" }}
                onClick={() => {
                  del.mutate(confirm, {
                    onSuccess: () => push({ kind: "success", text: "Backup deleted." }),
                    onError: (e) => push({ kind: "error", text: (e as Error).message }),
                  });
                  setConfirm(null);
                }}
              >Delete</button>
            </div>
          </div>
        </div>
      )}
    </SettingsSection>
  );
}
```

- [ ] **Step 3: Run the existing test to confirm still green**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/BackupsPage.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/BackupsPage.tsx
git commit -m "feat(frontend): restyle Backups page to Ledger system

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Restyle ExportPage to Ledger, fit under layout

**Files:**
- Modify: `frontend/src/pages/ExportPage.tsx`
- Test: `frontend/src/__tests__/ExportPage.test.tsx` (existing — must stay green)

**Contract to preserve** (existing tests + `e2e/pages/export.py`): a button named `/start export/i`; the scope checkboxes; the over-1GB warning text containing `consider deleting`; rows with `data-testid="export-row-{id}"`; "Download" link per done row. No second `<main>`.

- [ ] **Step 1: Run the existing test first (baseline green)**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ExportPage.test.tsx`
Expected: PASS (3 tests) before any change.

- [ ] **Step 2: Replace the file contents**

```tsx
// frontend/src/pages/ExportPage.tsx
import { useState } from "react";
import { useCreateExport, useDeleteExport, useExports } from "@/hooks/useExport";
import type { ExportScope } from "@/api/export";
import { SkeletonRows } from "@/components/Skeleton";
import { EmptyState } from "@/components/EmptyState";
import { useToast } from "@/hooks/useToast";
import SettingsSection from "@/components/settings/SettingsSection";

const ONE_GB = 1024 * 1024 * 1024;

function fmtSize(n: number | null): string {
  if (!n) return "—";
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function ExportPage() {
  const { data = [], isLoading } = useExports();
  const { push } = useToast();
  const create = useCreateExport();
  const del = useDeleteExport();
  const [scope, setScope] = useState<ExportScope>({
    threads: "all", snapshots: "all",
    observations: true, triggers: true, profiles: true, watchlists: true,
  });

  const totalBytes = data.filter((j) => j.status === "done").reduce((acc, j) => acc + (j.size_bytes ?? 0), 0);
  const overThreshold = totalBytes > ONE_GB;
  const anyRunning = data.some((j) => j.status === "pending" || j.status === "running");

  return (
    <SettingsSection title="Export" description="Bundle your data into a downloadable zip.">
      {overThreshold && (
        <div className="ledger-surface px-4 py-3 text-[13px] text-copper-200"
             style={{ borderColor: "var(--rule-strong)" }}>
          Exports currently occupy {fmtSize(totalBytes)}. Consider deleting old ones.
        </div>
      )}

      <div className="ledger-surface p-5 space-y-3">
        <h3 className="ledger-eyebrow">Choose what to include</h3>
        <div className="grid sm:grid-cols-2 gap-2">
          <ScopeCheck label="Threads (all)" checked={!!scope.threads}
                      onChange={(v) => setScope((s) => ({ ...s, threads: v ? "all" : undefined }))} />
          <ScopeCheck label="Snapshots (all)" checked={!!scope.snapshots}
                      onChange={(v) => setScope((s) => ({ ...s, snapshots: v ? "all" : undefined }))} />
          <ScopeCheck label="Observations" checked={!!scope.observations}
                      onChange={(v) => setScope((s) => ({ ...s, observations: v }))} />
          <ScopeCheck label="Triggers + firings" checked={!!scope.triggers}
                      onChange={(v) => setScope((s) => ({ ...s, triggers: v }))} />
          <ScopeCheck label="Profiles + Watchlists" checked={!!scope.profiles && !!scope.watchlists}
                      onChange={(v) => setScope((s) => ({ ...s, profiles: v, watchlists: v }))} />
        </div>
        <button
          className="ledger-cta disabled:opacity-50"
          disabled={create.isPending || anyRunning}
          onClick={() => create.mutate(scope, {
            onSuccess: () => push({ kind: "info", text: "Export job queued." }),
            onError: (e) => push({ kind: "error", text: (e as Error).message }),
          })}
        >
          {create.isPending ? "Queuing…" : "Start export"}
        </button>
      </div>

      <div>
        <h3 className="ledger-eyebrow mb-2">Recent exports</h3>
        {isLoading && <SkeletonRows rows={3} />}
        {!isLoading && data.length === 0 && (
          <EmptyState
            title="No exports yet"
            body="Pick what you'd like to bundle, then start an export. The zip builds asynchronously."
          />
        )}
        {data.length > 0 && (
          <div className="ledger-surface overflow-hidden">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-rule text-left">
                  {["Created", "Status", "Size", "Filename", ""].map((h, i) => (
                    <th key={i} className="px-4 py-2.5 font-mono text-[10px] uppercase tracking-wider text-copper-400">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-rule-soft">
                {data.map((j) => (
                  <tr key={j.id} data-testid={`export-row-${j.id}`}>
                    <td className="px-4 py-2.5 text-ink-300">{new Date(j.created_at).toLocaleString()}</td>
                    <td className="px-4 py-2.5">
                      {j.status === "running" || j.status === "pending"
                        ? <span className="text-copper-300">{j.status}…</span>
                        : j.status === "done" ? <span className="text-gain">done</span>
                        : <span className="text-loss" title={j.error}>{j.status}</span>}
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-ink-200">{fmtSize(j.size_bytes)}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-ink-200">{j.filename}</td>
                    <td className="px-4 py-2.5 text-right whitespace-nowrap">
                      {j.status === "done" && (
                        <>
                          <a className="text-copper-300 hover:text-copper-200 text-[12px] mr-4"
                             href={`/api/export/${j.id}/download/`}>Download</a>
                          <button className="text-loss hover:underline text-[12px]"
                                  onClick={() => del.mutate(j.id)}>Delete</button>
                        </>
                      )}
                      {j.status === "failed" && (
                        <button className="text-copper-300 hover:text-copper-200 text-[12px]"
                                onClick={() => create.mutate(j.scope as ExportScope)}>Retry</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </SettingsSection>
  );
}

function ScopeCheck({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-[13px] text-ink-200">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
             className="accent-[var(--copper-500)]" />
      <span>{label}</span>
    </label>
  );
}
```

- [ ] **Step 3: Run the existing test to confirm still green**

Run: `docker compose exec -T frontend pnpm exec vitest run src/__tests__/ExportPage.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ExportPage.tsx
git commit -m "feat(frontend): restyle Export page to Ledger system

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Update the E2E Settings page object

**Files:**
- Modify: `e2e/pages/settings.py`

The redesign renders one `Save` button per provider card, so the bare `get_by_role("button", name="Save")` is ambiguous. Scope it by the `provider-card-{provider}` testid. The `api_key_input` label lookup still works because each key field's label is `"<Provider> API key"` (case-insensitive substring match).

- [ ] **Step 1: Replace the file contents**

```python
"""Settings page — /settings (AI Providers section)."""

from __future__ import annotations

from playwright.sync_api import Locator

from e2e.pages.base import BasePage


class SettingsPage(BasePage):
    PATH = "/settings"

    def go(self) -> None:
        self.goto(self.PATH)

    def card(self, provider: str = "claude") -> Locator:
        return self.page.get_by_test_id(f"provider-card-{provider}")

    def api_key_input(self, provider: str) -> Locator:
        return self.page.get_by_label(f"{provider} API key")

    def save_btn(self, provider: str = "claude") -> Locator:
        return self.card(provider).get_by_role("button", name="Save")

    def nav_link(self, label: str) -> Locator:
        return self.page.get_by_role("link", name=label)

    def save_api_key(self, provider: str, key: str) -> None:
        self.api_key_input(provider).fill(key)
        self.save_btn(provider).click()
```

- [ ] **Step 2: Sanity-check Python imports compile**

Run: `docker compose exec -T web python -c "import ast; ast.parse(open('/app/e2e/pages/settings.py').read())"`
Note: if `/app/e2e` is not mounted in `web`, instead lint locally: `python -m py_compile e2e/pages/settings.py` on the host.
Expected: no output (parses cleanly).

- [ ] **Step 3: Commit**

```bash
git add e2e/pages/settings.py
git commit -m "test(e2e): scope Settings Save button per provider card

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 16: Full verification + visual baseline regeneration

**Files:** none created; regenerates `e2e/visual/__screenshots__/` baselines for the settings routes.

- [ ] **Step 1: Run the full gate**

Run: `make check`
Expected: ruff + ty + frontend lint pass; `pytest` + `vitest --run` pass. Fix any failures before continuing.

- [ ] **Step 2: Regenerate visual baselines for the changed routes**

The settings routes' screenshots (`settings_general`, `settings_backups`, `settings_export` in `e2e/visual/test_route_snapshots.py`) intentionally change. Baselines are root-owned, so regenerate via the make target (do not hand-edit):

Run: `make e2e-visual-update`
Then inspect: `git status --porcelain e2e/visual/__screenshots__/` and `git diff --stat e2e/visual/__screenshots__/`
Confirm only the three settings screenshots (and any legitimately affected) changed; eyeball them with an image viewer if possible.

- [ ] **Step 3: Run the a11y and ui lanes for the settings cluster**

Run: `make e2e`
Expected: `ui/api/ws/visual/a11y` lanes pass. In particular `e2e/a11y/test_axe_per_route.py` (covers `/settings/backups`, `/settings/export`) and `e2e/ui/test_settings.py` must pass. If axe reports new violations, fix the markup (labels/contrast) — do not suppress.

- [ ] **Step 4: Commit regenerated baselines**

```bash
git add e2e/visual/__screenshots__/
git commit -m "test(e2e): regenerate visual baselines for redesigned settings routes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Final confirmation**

Run: `make check`
Expected: PASS. The branch `feature/settings-redesign` is now ready for a PR.

---

## Notes & risks

- **Visual churn is expected** — Task 16 owns the baseline regeneration as a discrete, reviewable step.
- **`useUpsertProviderConfig` is shared** between the enable toggle and the Save button, so `isPending` briefly disables both on either action. Acceptable.
- **Schwab is the only Connections entry** — there is no endpoint for Finnhub/Marketaux keys, so none is built.
- **SideNav is intentionally unchanged** — the new sub-rail makes Backups/Export discoverable. Adding global SideNav entries is a trivial future change if desired.
- **Do not** reintroduce `api_key_write: ""` into the save body — that is the bug being fixed.
