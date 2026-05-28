# E2E hardening — gaps & skip triage report

Produced during the 2026-05-28 e2e hardening work (Phase 2). Lists every product/backend
gap surfaced by the now-honest tests, and the disposition of every remaining skip.

## Genuine product/UI gaps — tracked as `xfail`, for prioritization

These are real product holes the hardened tests exposed. Each is an `xfail(strict=False)`,
so it flips to **XPASS** (a visible signal) the moment the gap is closed. No backend code was
changed as part of the test work (out of scope).

| Test (xfail) | Gap | Where |
|---|---|---|
| `ui/test_profiles.py::test_profile_flags_editable_in_ui` | `/profiles` create form exposes only name/style/provider. `TradingProfile.enable_tools` / `enable_memory` / `thinking_budget` exist on the model and drive real AI behavior but **cannot be set from the UI**. | `frontend/src/pages/ProfilesPage.tsx` |
| `ui/test_profiles.py::test_profile_toggle_active` | No "activate" affordance on `/profiles` — a profile cannot be marked active from the list UI. | `frontend/src/pages/ProfilesPage.tsx` |
| `ui/test_files_and_citations.py::test_file_upload_and_attach_to_thread` | No standalone `/files` route exists. Upload UI lives only inside `ThreadDetailPage`'s `FileAttachPanel`. The `FilesPage` POM targets a dead `/files` route. | `frontend/src/router.tsx` |
| `ui/test_files_and_citations.py::test_delete_file_hits_anthropic_delete` | Same — no standalone `/files` route; delete UI is in `FileAttachPanel` only. | `frontend/src/router.tsx` |
| `ui/test_schwab_oauth.py::test_oauth_callback_persists_encrypted_token` | The Schwab `authorize`/`callback` views call `build_authorize_url()` / `exchange_code_for_token()` which hit the **real** Schwab endpoints — they are **not** intercepted by the scenario/mock engine, so no OAuth flow can complete headlessly under `MOCK_EXTERNAL`. | `backend/apps/secrets/views.py` (mock hook in `apps/core/mocks/providers.py` is never called) |

## Backend bugs surfaced (not xfail — flagged for fixing)

| Severity | Bug | Evidence / where |
|---|---|---|
| **High** | `observer.run_observer` Celery task crashes every fire: `FieldError: Cannot resolve keyword 'created_at' into field. Choices are: captured_at, …` — a query orders/filters `Snapshot` by `created_at`, but the model field is `captured_at`. Scheduled observer runs are failing. | Worker logs during e2e (`observer.run_observer[…] raised unexpected`). Grep `created_at` in the observer fire path / snapshot query. |
| Low | Fast no-stream `_fail(event="error")` (e.g. provider-disabled, ~20 ms) may not paint a failed bubble in the UI: the error branch doesn't `refetch()` and can be clobbered by the send mutation's `onSuccess`. The `cost_capped` path renders reliably. `test_provider_disabled_blocks_send` therefore asserts the gate at the DB layer. | `frontend/src/pages/ThreadDetailPage.tsx` `onWs` error branch; `apps/threads/tasks.py:_fail`. |
| Low (cosmetic) | Observer timeline's `isSkipped` dim/lock styling only matches messages whose text starts with `⏸`, but the real cost-cap skip message (`apps/observer/services/run.py`: `"Observer fire skipped at …: cost cap exceeded"`) does not — so real cost-cap skips render as ordinary entries. (The e2e seed now writes a `⏸`-prefixed message to exercise the styled path.) | `frontend/src/pages/ObserverTimelinePage.tsx`; `apps/observer/services/run.py`. |
| Low (tooling) | `tools/flake_audit.py` runs `docker compose exec` **without `-p $(E2E_PROJECT)`**, so locally it targets the default `ai-dashboard` (dev) project instead of the isolated e2e stack — wrong stack + pollutes dev. CI is unaffected (single stack), but the local invocation in `make`/docs should pass `-p`. | `tools/flake_audit.py:26` |

## Skip disposition (every remaining `pytest.skip` / guard)

**Removed / converted to hard assert (were stale or dead guards):**
- `ui/test_error_paths.py` ×2 — enabled-gate + cost-cap both fixed on origin/main → un-skipped.
- `ui/test_snapshots.py` — dead `≥2 ready snapshots` guard (seed makes 4) → removed.
- `ui/test_analytics.py` — ticker input is a placeholder not a label (POM bug) → fixed, skip removed.
- `ui/test_observer.py` — cost-cap message was seeded into the wrong (schedule-linked) thread → seed now targets the canonical per-profile thread → skip removed.
- `ui/test_keyboard_and_palette.py` — palette is mounted → try/except-skip → hard assert.
- `ui/test_threads.py` — pinned synthetic message is seeded → guard → hard assert.
- `ws/test_ws_reconnect.py` (`?since=` claim) — replay IS implemented → hard assert.
- `ws/test_snapshot_progress.py` — profile always seeded → hard assert.

**Kept — legitimate (environment / posture / deliberate flakiness defense):**
- `api/test_scenario_engine_disabled_in_prod.py` ×2 and `tests/test_scenario_engine.py` — prod-posture-only; skip when the e2e overlay is up (by design).
- `perf/test_lighthouse.py` ×2 — skip when docker/lighthouse isn't available in the runner.
- `a11y/test_keyboard_only.py` ×2 — skip when a nav target isn't reachable within the Tab-step budget (reachability probe, not a coverage hole).
- `ws/test_ws_reconnect.py:43` — skip if the mock stream produces no `text_delta` in-window; deliberate flakiness defense for a reconnect test (the replay assertion that follows is unconditional).

**Kept — dead defensive guards (never fire at runtime; tests pass):**
- `ws/test_notifications.py` — trigger/schedule "not found" + "endpoint not exposed" guards. The seeded objects and endpoints exist (all 3 notification tests pass), so these never fire. Left as cheap defense; could be tightened to hard asserts in a follow-up.
