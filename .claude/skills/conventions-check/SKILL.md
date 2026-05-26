---
name: conventions-check
description: >-
  Quick inline check of the current working changes against this repo's documented non-obvious
  conventions and silent-failure traps. Use before committing backend changes. Lighter-weight
  than dispatching the conventions-reviewer subagent (no separate agent spawned).
---

# Conventions check

Review the current diff against this repo's known silent-failure traps. Run `git diff HEAD`
(and `git diff --staged`) and check each item the change actually touches. Report `file:line` +
fix for real issues only.

- **Celery task registered?** New task module added to the explicit list in
  `backend/config/celery.py`? (No autodiscovery — unlisted tasks silently never run.)
- **Section status:** `SnapshotSection` terminal state is `"done"`; parent `Snapshot` is
  `"ready"`. No code filtering sections by `"ready"` or attaching images on the wrong state.
- **URL ordering:** new `config/urls.py` includes — specific `/api/<name>/` BEFORE generic `/api/`.
- **Providers:** obtained via `get_provider()` / router, never instantiated directly in
  views/tasks.
- **MOCK_EXTERNAL:** not added to `compose.yaml` / `.env` / dev settings (e2e overlay only).
- **Secrets:** no logging or non-`write_only` serialization of encrypted credential fields.
- **Binding:** nothing newly bound to `0.0.0.0` (no app auth; 127.0.0.1 only).
- **uv.lock:** updated if `pyproject.toml` dependencies changed.

For a deeper pass (reads files, traces context, checks migrations), dispatch the
`conventions-reviewer` subagent instead.
