# Presets fill objective only — remove `AgentPreset.default_includes`

- **Date:** 2026-06-25
- **Status:** Draft (pending user review)
- **Scope:** `apps.profiles` (model, serializer, migration), `frontend` (composer preset apply, preset form/list/types), OpenAPI schema.

## 1. Problem

In the snapshot composer, applying an `AgentPreset` ("snapshot template") via the
"Apply a preset…" dropdown changes **two** things: it fills the objective
(`onSetObjective(preset.objective_template)`) **and** overwrites the checked
section boxes (`onSetIncludes(preset.default_includes)`,
`SnapshotComposerPage.tsx:196`). The second behavior is unwanted — selecting a
preset should not silently rewrite which sections the user has chosen to capture.

Once a preset no longer applies its `default_includes`, that field has no
remaining consumer (no observer/schedule/trigger reads it — only the composer
apply path and the preset's own editor/list/serializer do), so it is removed
entirely.

## 2. Requirements (decided)

1. Applying a preset fills **only** the objective. The checked section boxes are
   left exactly as the user/profile had them.
2. `AgentPreset.default_includes` is removed **entirely** — model field +
   migration, serializer, FE editor/display, FE types, schema. A preset becomes
   `{name, slug, description, objective_template, structured, builtin, active}`.
3. `TradingProfile.default_includes` is a **separate** field and is unchanged —
   selecting a profile still sets the composer's initial boxes.
4. The manual `SnapshotSectionPicker` (the checkbox UI) and `objective_template`
   behavior are unchanged.

## 3. Backend changes

### 3.1 Model — `backend/apps/profiles/models.py`
Delete `default_includes = models.JSONField(default=list)` from `AgentPreset`
(line ~102). Keep `TradingProfile.default_includes` (line ~46).

### 3.2 Migration — `backend/apps/profiles/migrations/0009_remove_agentpreset_default_includes.py`
A single `migrations.RemoveField(model_name="agentpreset", name="default_includes")`
depending on `0008_seed_macro_fundamentals_preset`. Reversible (auto).

**Seed migrations need no edits.** `0005`/`0006`/`0008` seed builtins via
`apps.get_model("profiles", "AgentPreset")` (historical model state) inside
`RunPython`, and they run **before** this `RemoveField`. At their frozen state the
field still exists, so `get_or_create(defaults={... "default_includes": ...})`
continues to work on a fresh `migrate`; the column is dropped afterward.

### 3.3 Serializer — `backend/apps/profiles/serializers.py`
Remove `"default_includes"` from `AgentPresetSerializer.Meta.fields` (line ~60).
Regenerate `backend/schema.yml` (`make schema`) — drift-gated.

### 3.4 Tests — `backend/apps/profiles/tests/test_agent_presets.py`
Remove the `default_includes` assertions and inputs:
- the default-empty assertion (~line 52),
- the seed-verification test's per-preset `default_includes` expectation (~133-134) —
  drop the `default_includes` check; keep the rest of the seed assertions,
- the create round-trip input/assert (~164, 173),
- the update round-trip input/assert (~196, 200, 206),
- the "field present in response" assert (~229).
Keep all `objective_template`, `slug`, `builtin`, `active`, and duplicate-slug coverage.

## 4. Frontend changes

### 4.1 Composer — `frontend/src/pages/SnapshotComposerPage.tsx`
In `PresetField`, drop `onSetIncludes(preset.default_includes)` and remove the
`onSetIncludes` prop from the component and its call site (line ~357). The apply
handler calls only `onSetObjective(preset.objective_template)`. The "Reset to
placeholder" select-reset behavior stays.

### 4.2 Preset types — `frontend/src/api/presets.ts`
Remove `default_includes` from the `AgentPreset` type (line ~9) and the
create/update body type (line ~21).

### 4.3 Preset editor/list — `frontend/src/pages/profiles/`
- `PresetForm.tsx`: remove the section-checkbox editor block (the sections grid
  bound to `draft.default_includes`, line ~34) and its surrounding label.
- `PresetList.tsx`: remove the `default_includes.join(", ")` display line (~32).
- `usePresetForm.ts`: remove `default_includes` from the draft initializer (~25)
  and delete the section-toggle handler (~46).
- `types.ts`: remove `default_includes` from the preset draft type and its blank
  default (lines ~21, ~30). Do **not** touch the `ProfileDraft` `default_includes`.

### 4.4 Types regen — `frontend/src/api/schema.d.ts`
Regenerate via the known gen:api workaround (`pnpm gen:api` is broken in the
frontend container — copy `schema.yml` in and run `openapi-typescript` against it).
The `default_includes` property is removed from the AgentPreset schema only;
`TradingProfile`/observer schemas keep theirs.

### 4.5 FE tests
- `__tests__/hooks/useAgentPresets.test.tsx`: drop `default_includes` from fixtures.
- `__tests__/SnapshotComposerPage.test.tsx`: **change** the preset test — assert the
  objective textarea is filled from `objective_template` AND that the section
  checkboxes are **unchanged** after applying a preset; remove the old "preset's
  default_includes reflected in section checkboxes" assertion; drop
  `default_includes` from the preset fixture (~line 420).
- Any `PresetForm`/`PresetList` test asserting the sections editor/display — update
  to match the removed UI.

## 5. Out of scope
- `TradingProfile.default_includes` (profile→initial boxes) — unchanged.
- `SnapshotSectionPicker` (manual checkboxes) — unchanged.
- Preset `objective_template` behavior — unchanged.
- The historical seed migrations — not edited.

## 6. Risks / notes
- Removing `default_includes` from the preset API is a deliberate contract change;
  no observer/schedule/trigger consumes it, so blast radius is the preset feature
  only. Single-user, network-isolated app — no compat shim needed.
- Migration drops a JSON column on Postgres (fast metadata op); plain `RemoveField`,
  expected to pass the migration-safety (squawk) gate.
