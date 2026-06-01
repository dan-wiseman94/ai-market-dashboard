# Snapshot composer: split positions into Current vs. Potential

**Date:** 2026-06-01
**Status:** Design approved, ready for implementation plan

## Problem

The snapshot composer has a single free-text **Positions** field (`Snapshot.manual_positions`).
It conflates two distinct things a trader wants the AI to reason about:

- **Current holdings** — what you own now; the AI should help you *manage* them.
- **Potential trades** — candidates you're weighing; the AI should *evaluate the entry case*,
  not assume they're held.

Because both arrive in one undifferentiated block, the AI can't reliably tell which is which,
and the user can't express "here's what I hold" separately from "here's what I'm considering."

## Goal

Add a second free-text positions field so the composer captures **Current positions** and
**Potential positions to discuss** separately, each framed distinctly in the AI payload.

## Non-goals (YAGNI)

- Structured position entry (ticker/qty/entry rows). Stay free-text — the AI parses it, matching
  the existing convention everywhere else in the app.
- Wiring `current positions` to the `apps.portfolio` tracker (it isn't routed yet; out of scope).
- Surfacing candidate positions downstream into theses/predictions/coach.
- `AgentPreset` / profile defaults for the new field.

## Design

Mirror the existing `manual_positions` plumbing end-to-end. One new field, no DB rename.

### 1. Data model — `apps/snapshots/models.py`

- Keep `manual_positions` as-is; it is the **Current positions** field. No rename (preserves
  back-compat, avoids a data migration on existing rows).
- Add:
  ```python
  # Free-text candidate trades the user is weighing; the AI evaluates the entry case.
  candidate_positions = models.TextField(blank=True, default="")
  ```
- New additive migration `0013_snapshot_candidate_positions` (default `""`, safe on existing rows).
  (Latest existing migration is `0012_alter_snapshotsection_kind`.)

### 2. AI payload framing — `apps/snapshots/serializer.py`

The point of the split. Emit two distinctly-headed blocks so the model reasons differently:

- Existing `manual_positions` block — label tightened to make "held" explicit:
  ```
  ## Positions (current holdings — manually entered; parse and reason over these)
  <manual_positions>
  ```
- New `candidate_positions` block — emitted **only when non-empty**, placed immediately after
  the current-holdings block:
  ```
  ## Candidate positions (potential trades under consideration — evaluate the entry case, do not assume these are held)
  <candidate_positions>
  ```

### 3. API plumbing

- `apps/snapshots/serializers.py`: add `"candidate_positions"` to the serializer field list.
- `apps/snapshots/views.py` create: `candidate_positions=data.get("candidate_positions", "")`.

### 4. Frontend

- `frontend/src/api/snapshots.ts`: add `candidate_positions?: string` to the create-snapshot
  request type.
- `frontend/src/hooks/useCreateSnapshot.ts`: pass it through (if the hook types the body
  explicitly).
- `frontend/src/pages/SnapshotComposerPage.tsx`:
  - Rename the existing textarea label to **"Current positions (optional, free text)"**
    (state stays `manualPositions`, payload key stays `manual_positions`).
  - Add a second textarea **"Potential positions to discuss (optional, free text)"** bound to a
    new `candidatePositions` state, sent as `candidate_positions` in the create payload.
    Placeholder e.g. *"Trades you're weighing — e.g. long NVDA 6mo, short QQQ hedge"*.

### 5. Tests

- Backend `apps/snapshots/tests/test_serializer.py` — two new tests mirroring the existing
  `manual_positions` pair: candidate block rendered with its framing when present; omitted when
  blank.
- Frontend `SnapshotComposerPage.test.tsx` — assert the new textarea's value posts as
  `candidate_positions` in the create payload.

## Files touched

| File | Change |
|---|---|
| `backend/apps/snapshots/models.py` | add `candidate_positions` field |
| `backend/apps/snapshots/migrations/0013_snapshot_candidate_positions.py` | new migration |
| `backend/apps/snapshots/serializer.py` | render candidate block with distinct framing |
| `backend/apps/snapshots/serializers.py` | expose `candidate_positions` |
| `backend/apps/snapshots/views.py` | read `candidate_positions` on create |
| `backend/apps/snapshots/tests/test_serializer.py` | 2 new tests |
| `frontend/src/api/snapshots.ts` | request type field |
| `frontend/src/hooks/useCreateSnapshot.ts` | pass-through (if typed) |
| `frontend/src/pages/SnapshotComposerPage.tsx` | relabel + new textarea |
| `frontend/src/__tests__/SnapshotComposerPage.test.tsx` | assert payload |
