# Presets fill objective only — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Applying a snapshot preset fills only the objective (never the checked section boxes), and the now-unused `AgentPreset.default_includes` field is removed end-to-end.

**Architecture:** Two cohesive changes. (1) Backend: drop `AgentPreset.default_includes` (model + migration + serializer + tests) and regenerate both schema files. (2) Frontend: the composer's preset apply stops calling `onSetIncludes`, and `default_includes` is removed from the preset type, editor form, list display, draft state, and tests. `TradingProfile.default_includes` (profile→initial boxes) is untouched.

**Tech Stack:** Django 5 + DRF, Postgres 16, pytest, React + TypeScript + vitest, openapi-typescript. Everything runs in Docker Compose.

## Global Constraints

- **All commands run in Docker.** Backend: `docker compose exec web pytest apps/<app>/tests/test_<x>.py::<name> -v` (container WORKDIR `/app/backend` — drop the `backend/` prefix). FE: `docker compose exec frontend pnpm exec vitest run <path> -t "name"`. Dev stack must be up: `make dev`. Host/editor "module not found"/JSX diagnostics are environmental noise, not findings.
- **Spec:** `docs/superpowers/specs/2026-06-25-preset-includes-removal-design.md` — re-read the relevant section per task.
- **Keep `TradingProfile.default_includes`** (`models.py:46`, profile→initial composer boxes) and the `SnapshotSectionPicker` (manual checkboxes). Only `AgentPreset.default_includes` and the composer's preset-apply-includes behavior are removed.
- **Preset shape after this change:** `{name, slug, description, objective_template, structured, builtin, active}` — `objective_template` behavior unchanged.
- **Seed migrations are NOT edited** — `0005`/`0006`/`0008` seed builtins via `apps.get_model` (historical state) and run before the new `RemoveField`, so they stay valid.
- **Dev-DB note:** a parallel branch (`feat/snapshot-24h-window`) applied `snapshots.0014` to the dev DB; that migration file is absent on this branch. Any "applied migration not in files" warning for **snapshots** during `make migrate` is expected and harmless here — it does not affect the **profiles** migration. Tests use a fresh test DB built from this branch's files.
- **gen:api landmine:** `pnpm gen:api` is broken in the frontend container (`../backend/schema.yml` unresolvable). Regenerate FE types by copying the schema in: `docker compose cp backend/schema.yml frontend:/tmp/schema.yml && docker compose exec -w /app frontend pnpm exec openapi-typescript /tmp/schema.yml -o src/api/schema.d.ts`.
- **Commits:** conventional, end with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Branch `feat/preset-no-includes` (already created off `main`).
- **Quality gates** (`make check`): ruff + mypy (zero-baseline, real gate) + import-linter + deptry + semgrep-rules + pytest; FE eslint + tsc + vitest + depcruise + type-coverage; OpenAPI drift gate (`schema.yml` + `schema.d.ts`); migration-safety (squawk). `ty` is advisory (ignore its exit code).

---

## File Structure

**Backend** — `backend/apps/profiles/`
- `models.py` — remove `AgentPreset.default_includes` (keep `TradingProfile.default_includes`).
- `migrations/0009_remove_agentpreset_default_includes.py` — new, `RemoveField`.
- `serializers.py` — remove `"default_includes"` from `AgentPresetSerializer.Meta.fields`.
- `tests/test_agent_presets.py` — drop `default_includes` assertions/inputs + the `EXPECTED_INCLUDES` test.

**Schema** — `backend/schema.yml`, `frontend/src/api/schema.d.ts` (regenerated).

**Frontend** — `frontend/src/`
- `pages/SnapshotComposerPage.tsx` — `PresetField` stops applying includes.
- `api/presets.ts` — drop `default_includes` from the preset + body types.
- `pages/profiles/PresetForm.tsx` — remove the sections editor block.
- `pages/profiles/PresetList.tsx` — remove the includes display line.
- `pages/profiles/usePresetForm.ts` — remove `default_includes` from draft + the toggle handler.
- `pages/profiles/types.ts` — remove `default_includes` from `PresetDraft` + `BLANK_PRESET_DRAFT`.
- `__tests__/SnapshotComposerPage.test.tsx`, `__tests__/hooks/useAgentPresets.test.tsx`, `__tests__/ProfilesPage.test.tsx` — update preset fixtures/assertions.

---

## Task 1: Backend — remove `AgentPreset.default_includes` (+ regen schema)

**Files:**
- Modify: `backend/apps/profiles/models.py`, `backend/apps/profiles/serializers.py`, `backend/apps/profiles/tests/test_agent_presets.py`
- Create: `backend/apps/profiles/migrations/0009_remove_agentpreset_default_includes.py`
- Regenerate: `backend/schema.yml`, `frontend/src/api/schema.d.ts`

**Interfaces:**
- Produces: `AgentPreset` has no `default_includes`; `AgentPresetSerializer` no longer returns it; `/api/presets/` payloads omit it.

- [ ] **Step 1: Update the backend tests first (they encode the contract)**

In `backend/apps/profiles/tests/test_agent_presets.py`:

(a) In `test_defaults` (~line 44), delete the line:
```python
    assert preset.default_includes == []
```

(b) Delete the `EXPECTED_INCLUDES` dict (~lines 102-119) and the whole `test_seed_migration_includes_correct` function (~lines 129-135).

(c) In `test_create_custom_preset` (~line 160), remove `"default_includes": ["quotes", "ohlc"],` from the `payload` and delete the assertion `assert body["default_includes"] == ["quotes", "ohlc"]`.

(d) In `test_patch_preset` (~line 192), remove `default_includes=["quotes"],` from the `AgentPreset.objects.create(...)`, remove `"default_includes": ["quotes", "news"]` from the PATCH body (leave `"objective_template": "Updated objective."`), and delete `assert preset.default_includes == ["quotes", "news"]`.

(e) In `test_retrieve_single_preset` (~line 220), delete `assert "default_includes" in body`.

- [ ] **Step 2: Run the tests to verify they fail (field still present)**

Run: `docker compose exec web pytest apps/profiles/tests/test_agent_presets.py -v`
Expected: the edited file still imports/runs, but `test_create_custom_preset`/`test_patch_preset` now FAIL or error because the model/serializer still carry `default_includes` (e.g. the serializer returns the field, or the create still persists it) — i.e. the contract the tests now assert (absence) isn't met yet. (If they happen to pass because absence isn't asserted, that's fine — Step 4 is the real gate.)

- [ ] **Step 3: Remove the field from the model + serializer**

In `backend/apps/profiles/models.py`, delete from `AgentPreset` (~line 102):
```python
    default_includes = models.JSONField(default=list)
```
Also update the `AgentPreset` docstring (~line 96) from:
```python
    """A capture template that pre-fills the snapshot composer's objective text and section includes."""
```
to:
```python
    """A capture template that pre-fills the snapshot composer's objective text."""
```

In `backend/apps/profiles/serializers.py`, delete `"default_includes",` from `AgentPresetSerializer.Meta.fields` (~line 60).

- [ ] **Step 4: Generate the migration**

Run: `make makemigrations`
Expected: creates `backend/apps/profiles/migrations/0009_remove_agentpreset_default_includes.py`. Verify it matches:
```python
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("profiles", "0008_seed_macro_fundamentals_preset"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="agentpreset",
            name="default_includes",
        ),
    ]
```
If `makemigrations` emits anything beyond this single `RemoveField`, STOP and report (it signals a stray model change).

- [ ] **Step 5: Apply + verify migrations and tests**

Run: `make migrate`
Expected: applies `profiles.0009` cleanly. (A harmless "applied migration not in files" note for **snapshots.0014** may appear — see Global Constraints; ignore it.)
Run: `make check-migrations`
Expected: no missing migrations.
Run: `docker compose exec web pytest apps/profiles/tests/test_agent_presets.py -v`
Expected: PASS (all remaining tests green; `default_includes` gone).

- [ ] **Step 6: Regenerate both schema files**

Run: `make schema`
Then confirm the boolean… (preset field) removal:
Run: `git diff backend/schema.yml | grep -n default_includes`
Expected: only deletions (`-` lines) under the AgentPreset schema (the `TradingProfile`/observer `default_includes` stay).
Regenerate FE types (gen:api landmine):
```bash
docker compose cp backend/schema.yml frontend:/tmp/schema.yml
docker compose exec -w /app frontend pnpm exec openapi-typescript /tmp/schema.yml -o src/api/schema.d.ts
```
Run: `git diff frontend/src/api/schema.d.ts | grep -n default_includes`
Expected: only deletions under the AgentPreset schema.

- [ ] **Step 7: Commit**

```bash
git add backend/apps/profiles/models.py backend/apps/profiles/serializers.py backend/apps/profiles/tests/test_agent_presets.py backend/apps/profiles/migrations/0009_remove_agentpreset_default_includes.py backend/schema.yml frontend/src/api/schema.d.ts
git commit -m "$(printf 'refactor(profiles): drop AgentPreset.default_includes (model, serializer, schema)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Frontend — preset apply fills objective only; remove the sections field

**Files:**
- Modify: `frontend/src/pages/SnapshotComposerPage.tsx`, `frontend/src/api/presets.ts`, `frontend/src/pages/profiles/PresetForm.tsx`, `frontend/src/pages/profiles/PresetList.tsx`, `frontend/src/pages/profiles/usePresetForm.ts`, `frontend/src/pages/profiles/types.ts`
- Test: `frontend/src/__tests__/SnapshotComposerPage.test.tsx`, `frontend/src/__tests__/ProfilesPage.test.tsx`, `frontend/src/__tests__/hooks/useAgentPresets.test.tsx`

**Interfaces:**
- Consumes: the `/api/presets/` payload (no `default_includes`) from Task 1.
- Produces: `AgentPreset`/`CreatePresetBody` TS types without `default_includes`; `PresetDraft` without it; preset apply only sets the objective.

- [ ] **Step 1: Update the composer test (assert objective-only, boxes unchanged)**

In `frontend/src/__tests__/SnapshotComposerPage.test.tsx`:

(a) Remove `default_includes: ["quotes", "news"],` from the `PRESET_A` fixture (~line 442).

(b) Replace the test `"selecting a preset fills objective and sections"` (~lines 475-495) with one that asserts the objective is filled and the section boxes are NOT changed by the preset. Note: the test's `useProfiles` mock auto-selects profile 1 (`Day Trader`, `default_includes: ["quotes","ohlc"]`) on render, overriding the `useState` default — so the effective initial boxes are `["quotes","ohlc"]`; the hardened test asserts a profile-checked box like `ohlc` is preserved after applying the preset:
```tsx
  it("selecting a preset fills objective only, leaving section boxes unchanged", async () => {
    const user = userEvent.setup();
    mockUseAgentPresets.mockReturnValue({ data: [PRESET_A] } as never);
    renderComposer();

    // Capture which section boxes are checked before applying the preset.
    const positionsBefore = (screen.getByRole("checkbox", { name: /positions/i }) as HTMLInputElement).checked;

    const presetSelect = screen.getByLabelText("Apply a preset");
    await user.selectOptions(presetSelect, String(PRESET_A.id));

    // Objective is filled from the preset's template.
    const objectiveTextarea = screen.getByPlaceholderText(/what do you want/i);
    expect(objectiveTextarea).toHaveValue(PRESET_A.objective_template);

    // Section boxes are untouched by the preset.
    expect((screen.getByRole("checkbox", { name: /positions/i }) as HTMLInputElement).checked).toBe(positionsBefore);
  });
```

- [ ] **Step 2: Run the composer test to verify it fails**

Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotComposerPage.test.tsx -t "fills objective only"`
Expected: FAIL — the current `PresetField` still calls `onSetIncludes`, so applying the preset changes the boxes (and/or a TS error on the removed `default_includes` fixture field once the type is updated). (At this point the TS type still has the field, so the failure is behavioral.)

- [ ] **Step 3: Stop applying includes in the composer**

In `frontend/src/pages/SnapshotComposerPage.tsx`:

(a) Change the `PresetField` signature to drop `onSetIncludes` (~lines 206-214):
```tsx
function PresetField({
  presets,
  onSetObjective,
}: {
  presets: ReturnType<typeof useAgentPresets>["data"];
  onSetObjective: (v: string) => void;
}) {
```

(b) In the `onChange` handler (~lines 224-227), remove the includes call so only the objective is set:
```tsx
          const preset = activePresets.find((p) => String(p.id) === e.target.value);
          if (preset) {
            onSetObjective(preset.objective_template);
          }
```

(c) At the `PresetField` usage (~line 389), remove the `onSetIncludes` prop:
```tsx
        <PresetField presets={presets} onSetObjective={setObjective} />
```

- [ ] **Step 4: Remove `default_includes` from the preset types and editor**

In `frontend/src/api/presets.ts`: delete `default_includes: string[];` from the `AgentPreset` type (~line 9) and from `CreatePresetBody` (~line 21).

In `frontend/src/pages/profiles/types.ts`: delete `default_includes: string[];` from `PresetDraft` (~line 21) and `default_includes: ["quotes", "positions", "breadth"],` from `BLANK_PRESET_DRAFT` (~line 30). Leave `Draft`/`BLANK_DRAFT` (profiles) and `PRESET_SECTION_OPTIONS` untouched for now — `PRESET_SECTION_OPTIONS` becomes unused after the next edit; remove it too if eslint/tsc flags it as unused.

In `frontend/src/pages/profiles/usePresetForm.ts`: remove `default_includes: p.default_includes,` from the `startEdit` draft (~line 25) and delete the `toggleSection` function (~lines 45-46); remove `toggleSection` from the returned object (~line 48). Remove the now-unused `toggleInArray` import if eslint flags it.

In `frontend/src/pages/profiles/PresetForm.tsx`: remove the entire "Default sections" `<div>` block (~lines 27-41) and drop `toggleSection` from the destructured `form` (~line 5). Remove the now-unused `PRESET_SECTION_OPTIONS` import (~line 1) if eslint flags it.

In `frontend/src/pages/profiles/PresetList.tsx`: delete the includes display line (~line 32):
```tsx
              <div className="text-xs text-slate-400">{p.default_includes.join(", ")}</div>
```

- [ ] **Step 5: Update the remaining FE tests**

In `frontend/src/__tests__/hooks/useAgentPresets.test.tsx`: remove the `default_includes: [...]` lines from the fixtures (~lines 17, 64, 78).

In `frontend/src/__tests__/ProfilesPage.test.tsx`:
- Remove `default_includes: [...]` from the `PRESET_A` (~line 329) and `BUILTIN_PRESET` (~line 343) fixtures.
- In `"lists presets with name and includes"` (~line 357): remove the includes assertion `expect(screen.getByText(/quotes.*ohlc.*news/)).toBeInTheDocument();` (~line 362) and rename the test to `"lists presets with name"`.
- In `"submitting the preset form calls createPreset.mutate with the right body"` (~line 377): remove `default_includes: expect.arrayContaining(["quotes"]),` from the `toMatchObject({...})` (~line 397).

- [ ] **Step 6: Verify FE compiles and tests pass**

Run: `docker compose exec -w /app frontend pnpm exec tsc --noEmit`
Expected: no errors (adjust `-w` if needed; if a "declared but never used" error appears for `PRESET_SECTION_OPTIONS`/`toggleInArray`, remove that import).
Run: `docker compose exec frontend pnpm exec vitest run src/__tests__/SnapshotComposerPage.test.tsx src/__tests__/ProfilesPage.test.tsx src/__tests__/hooks/useAgentPresets.test.tsx`
Expected: PASS.
Run: `git grep -n "default_includes" frontend/src/pages/profiles frontend/src/pages/SnapshotComposerPage.tsx frontend/src/api/presets.ts`
Expected: no matches (all preset-side references gone; profile `default_includes` lives elsewhere).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/SnapshotComposerPage.tsx frontend/src/api/presets.ts frontend/src/pages/profiles/PresetForm.tsx frontend/src/pages/profiles/PresetList.tsx frontend/src/pages/profiles/usePresetForm.ts frontend/src/pages/profiles/types.ts frontend/src/__tests__/SnapshotComposerPage.test.tsx frontend/src/__tests__/ProfilesPage.test.tsx frontend/src/__tests__/hooks/useAgentPresets.test.tsx
git commit -m "$(printf 'feat(profiles): preset apply fills objective only; drop preset sections from UI\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: Full gates + conventions check

**Files:** none (verification only)

- [ ] **Step 1: Schema drift**

Run: `make schema && git diff --exit-code backend/schema.yml`
Expected: exit 0 (no diff — already regenerated in Task 1).

- [ ] **Step 2: Full gates**

Run: `make check`
Expected: green on all real gates (ruff, mypy zero-baseline, import-linter, deptry, semgrep-rules, pytest; FE eslint/tsc/vitest/depcruise/type-coverage; OpenAPI drift). `ty`'s advisory non-zero exit is not a failure. If a real gate fails on a mechanical issue (unused import the edits exposed, a stale assertion), fix it, re-run the focused check, then re-run `make check`. If a failure indicates a real regression, STOP and report.

- [ ] **Step 3: Conventions check**

Invoke the `conventions-check` skill (or dispatch the `conventions-reviewer` subagent) on the working changes. Confirm no silent-failure landmines (this change touches no Celery task, snapshot section status, URL ordering, provider, or secret path — expect clean).

- [ ] **Step 4: Final commit (only if Step 2/3 required fixes)**

```bash
git add -A
git commit -m "$(printf 'chore(profiles): satisfy gates for preset-includes removal\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage:**
- §2.1 preset apply fills objective only → Task 2 (Step 3). ✓
- §2.2 remove `AgentPreset.default_includes` entirely (model/migration/serializer/FE/types/schema) → Task 1 (model/migration/serializer/schema) + Task 2 (FE types/editor). ✓
- §2.3 keep `TradingProfile.default_includes` → Global Constraints + not touched by any task. ✓
- §2.4 `SnapshotSectionPicker` + `objective_template` unchanged → not touched. ✓
- §3.1 model field removal → Task 1 Step 3. §3.2 migration (no seed edits) → Task 1 Step 4, Global Constraints. §3.3 serializer + schema → Task 1 Steps 3,6. §3.4 backend tests → Task 1 Step 1. ✓
- §4.1 composer apply → Task 2 Step 3. §4.2 presets.ts types → Task 2 Step 4. §4.3 PresetForm/List/usePresetForm/types → Task 2 Step 4. §4.4 schema.d.ts regen → Task 1 Step 6. §4.5 FE tests → Task 2 Steps 1,5. ✓
- §5 out of scope → respected. ✓

**Placeholder scan:** none — every step shows the exact edit or a content-anchored change with line refs (`~` because line numbers shift as edits land within a task).

**Type consistency:** `PresetField` loses `onSetIncludes` in both its definition (Task 2 Step 3a) and call site (3c). `AgentPreset`/`CreatePresetBody`/`PresetDraft`/`BLANK_PRESET_DRAFT` all lose `default_includes` together (Task 2 Step 4), and every consumer (PresetForm, usePresetForm, PresetList, composer, tests) is updated in the same task — no dangling reference. Backend serializer field list (Task 1) matches the model (Task 1). ✓
