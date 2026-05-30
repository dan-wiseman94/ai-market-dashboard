# M1 — Visible Second Brain (detailed design)

**Parent:** `2026-05-30-improvement-program-design.md`. **Effort:** M. **Depends on:** nothing.

**Premise:** the intelligence is built; it's hidden. Eight workstreams: W1–W4 surface existing-but-
invisible capability or wire already-built-but-dead pipes; W5–W8 (folded from M6, per user) make the
Decision Coach itself *good* and *ubiquitous* in the same pass — because all four touch
`apps/threads/coach.py` and it's wasteful to visit it twice. Net theme: the coach becomes **visible**
(W1/W2/W4), **good** (W6 semantic recall, W7 lessons), and **everywhere** (W8 triggers, W5 coverage).
All read-paths reuse existing hooks/services; new backend is thin (one analytics endpoint, one dashboard
aggregator, plus in-place edits to `coach.py` + the trigger fire path).

---

## W1 — Track record at decision time *(S, NEW)*

The single best value/effort item: `track_record_for_ticker()` already exists and is tested in
`apps/analytics/services/calibration.py`, but is only consumed by the coach prompt — no endpoint, no UI.

**Backend.** Add `GET /api/analytics/track-record/?ticker=<T>&direction=<bull|bear>&conviction=<1-5>`
(direction/conviction optional) → thin view wrapping the existing function. Register in
`apps/analytics/urls.py` **after** existing specific routes (URL-order convention). Read-only.
Response shape (mirror what the function returns):
```json
{ "ticker": "NVDA", "n": 12, "wins": 7, "losses": 5, "hit_rate": 0.58,
  "by_conviction": [{"conviction":5,"n":4,"wins":2,"hit_rate":0.5}, ...],
  "by_direction": {"bull":{"n":8,"hit_rate":0.62},"bear":{"n":4,"hit_rate":0.5}} }
```
(Exact keys follow the function's real return; the view must not re-implement logic.)

**Frontend.** `useTrackRecord(ticker, opts)` in `frontend/src/hooks/useAnalytics.ts` (debounced).
Render: (a) inline in `frontend/src/pages/thread-detail/ThesisForm.tsx` the moment a ticker is entered
("Your last 5 NVDA calls: 3W/2L · conviction-4 bullish 4/7"); (b) a card on `ThesisDetailPage.tsx`.

**Tests.** Backend: endpoint returns the function's output, empty-ticker → honest empty (n=0), URL
ordering doesn't shadow existing analytics routes. Frontend: hook + ThesisForm render with mock data.

## W2 — Structured-observation cards in the main thread *(S–M, OVERLAPS ObservationReportCard)*

`ObservationReportCard` renders only on `ObserverTimelinePage`; the consult thread renders flat markdown
because `StreamingMessage` reads only `content.text`, never `content.kind`/`content.report`.

**Frontend.** Thread `content.kind === "structured_observation"` carries `{report}` (per CLAUDE.md).
Carry `content.kind`/`report` through `frontend/src/pages/thread-detail/useLiveMessages.ts` →
`types.ts` (`LiveMessage`) → `Conversation.tsx`, which renders `ObservationReportCard` when present,
markdown otherwise. Re-theme `ObservationReportCard` from `emerald/rose/slate` to ledger tokens
(verify against `tailwind.config.ts`).

**Tests.** vitest: a structured-observation message renders the card; a plain message renders markdown
(fallback). No backend change.

## W3 — Live capture progress (+ reconnect replay decision) *(S–M, DEEPENS-BACKLOG)*

`snapshot.<id>` is emit-only: backend broadcasts per-section progress
(`apps/snapshots/services/__init__.py`), no subscriber. `SnapshotComposerPage` blocks on a 600 ms HTTP
poll (`waitForSnapshotReady`) showing a static "Capturing…" for up to 2 min.

**Frontend.** Subscribe the composer to `snapshot.<id>` via `useChannel` after create returns the id
(202 + id). New `SnapshotCaptureProgress` checklist (per-section ✓/⏳/✗, incl. partial-failure).
**Keep the HTTP poll as the terminal source of truth** — WS is progress-only.

**`?since=` decision (this milestone makes the call):** the server replay buffer
(`apps/threads/event_log.py`, `ThreadConsumer`) is fully built but the client never sends `since=`.
**Decision: wire it** for `thread.<id>` — track the last received `seq` in `WebSocketProvider` and append
`?since=<seq>` on reconnect so a mid-stream reconnect replays missed deltas. (If wiring proves fiddly,
fall back to the explicit alternative: delete the dead buffer + update CLAUDE.md §3.3 — do not leave it
ambiguous.) This is the riskiest sub-item; sequence it last in W3 and gate on a WS-lane test.

**Tests.** WS/vitest: progress events update the checklist; reconnect with a tracked seq sends `since=`
and replays (or the deletion path removes the route + buffer and a test asserts they're gone).

## W4 — Command-center Dashboard + live tiles *(M, DEEPENS-BACKLOG)*

`Dashboard.tsx` shows only `MarketContextStrip` + ephemeral broker `PositionsTable` + `RecentTriggersCard`
(30 s poll) and subscribes to **zero** WS channels. It surfaces none of theses/observer/briefing.

**Backend.** One aggregating endpoint (e.g. `GET /api/dashboard/` or a `apps/briefing`-style view) to
avoid N client round-trips, returning: open theses with live price + `pct_to_target`/distance-to-
invalidation (reuse the briefing's `assemble.py` `_theses_section` logic — do not duplicate), today's
observer runs + next scheduled fire, the latest briefing one-line summary, armed-trigger count + latest
firings, and the 7-day events row. Degrade gracefully per-section (briefing pattern: never raise).

**Frontend.** Replace the lower grid with tiles in `frontend/src/components/dashboard/`
(`OpenThesesTile`, `ObserverTodayTile`, `BriefingSummaryTile`, `ArmedTriggersTile`, `UpcomingEventsRow`),
each `EmptyState`-guarded and deep-linking into its surface. Reuse existing hooks where simpler than the
aggregate (`useSchedules`, `useUpcomingEvents`, `useLatestBriefing`, `RecentTriggersCard`).

**Live tiles.** Add `notifications` to `pathForChannel` in `WebSocketProvider.tsx`; migrate
`NotificationBell`'s ad-hoc raw `WebSocket` to the shared `Broker`/`useChannel`; subscribe the dashboard
(and bell) to `user.anonymous.notifications` so observer-completion / trigger-fire / backup events update
tiles in place. `ConnectionStatusDot` can then reflect the shared socket.

**Tests.** Backend: aggregator returns each section, degrades when a sub-source raises. Frontend: tiles
render from mock aggregate; a notification WS event updates the relevant tile; empty states hold.

## Coach upgrades (W5–W8) — folded from M6

**Verified coverage map (probe 2026-05-30).** `build_system_prompt` (base framing + live clock) is in
`_build_request` (`apps/threads/_request.py:135`) → **every** AI turn gets it. The rich stateful block
`assemble_coach_context` runs in only two places: `ThreadViewSet.create` when a thread is opened with a
pinned snapshot (`apps/threads/views.py:84`) and observer fires (`apps/observer/services/run.py:100`,
structured path at `:182`). Therefore the stateful block does **not** reach: the **trigger fire path**
(`apps/triggers/tasks.py` posts a bare `serialize_for_ai` user turn) → fixed by **W8**; **plain chat
threads with no snapshot** (no "situation" to anchor) → **deferred to M6** (needs a snapshot-free
situation definition); **follow-up turns** inherit the create-time block via thread history (present but
stale) → acceptable for M1, per-turn refresh **deferred to M6** (interacts with token budget + eval).

### W5 — Coverage consistency + `enable_coach` audit *(S)*
Make coverage a documented invariant, not folklore. Ensure every place that injects coach context honors
`profile.enable_coach` identically (kill switch parity), record the coverage map above as a module
docstring/comment in `apps/threads/coach.py`, and add a regression test asserting the trigger path (W8)
and observer path both produce a coach block for a snapshot with a `primary_ticker`. No new surface; this
is the guardrail that keeps W6–W8 honest.

### W6 — Semantic coach recall *(S, DEEPENS Decision Coach/recall) — highest quality/token win*
`coach._recall_block` (`apps/threads/coach.py:174-187`) calls `related_to_ticker()`
(`apps/recall/services/search.py:67-71`) = pure recency (`ORDER BY -source_created_at`); it never touches
the embedding. Swap to the existing semantic `search()` (`search.py:38-46`) seeded by a **compact
situation query** (primary ticker + snapshot headline numbers + open-thesis text), filtered to
`kinds=["postmortem","thesis","observation"]`, ticker-scoped, with a light recency tiebreak. Add a thin
`related_to_situation(ticker, query, k, kinds)` helper in `apps/recall/services/search.py` if cleaner than
calling `search()` directly. **Verify the exact `kind` constants** against `apps/recall/` during impl.
*Degrades cleanly:* `search()` already falls back to FTS when fastembed is unavailable, and `_safe()`
wraps the block. *Token discipline:* cap the query string and `k` (≤ current).
*Tests:* given indexed docs, the coach surfaces the *situation-matched* doc over a newer-but-irrelevant one;
FTS-fallback path still returns; empty corpus → "".

### W7 — Lessons-learned block *(S, DEEPENS Decision Coach)*
Post-mortem `lessons`/`what_missed` reach generation only incidentally today. Add `_lessons_block(ticker)`
to `assemble_coach_context` rendering the top-2 **decisive** post-mortems for the ticker
(`PostMortem.objects.filter(thesis__ticker=ticker, status="done", verdict__in=["correct","incorrect"]).order_by("-completed_at")[:2]`)
× ≤2 bullets each from `report["lessons"]`/`report["what_missed"]`, tagged with verdict + horizon
(e.g. *"30d (incorrect): under-weighted earnings-gap risk."*). **Lazy-import** `apps.thesis.models.PostMortem`
(threads→thesis cycle rule). **Look-ahead-safe by construction:** a horizon-H post-mortem only completes
≥ H days after `thesis.opened_at`, and we read only `status="done"`, so a lesson injected today derives
only from theses opened ≥ 7–90 days ago. *Token discipline:* hard cap 2×2. *Tests:* decisive PM →
bullets rendered with verdict/horizon; no PM / cold-start → ""; `inconclusive`/open PM excluded; block
never raises (`_safe`). Distinct from W1 track-record (numbers) — this gives *reasons*.

### W8 — Coach on the trigger path *(S, DEEPENS Decision Coach)*
`apps/triggers/tasks.py` (`_do_fire`, ~`:184-195`) posts a bare `serialize_for_ai` user turn — unlike
observer/ThreadViewSet it never calls `assemble_coach_context`. Triggers fire exactly when priors matter
most. Add `coach = assemble_coach_context(snap, trigger.profile)` and prepend it to the user message,
mirroring `apps/observer/services/run.py:100-108` (respect `enable_coach`). **Verify** `trigger.profile`
exists and that trigger snapshots carry a `primary_ticker` (if no `quotes` section, primary_ticker may be
empty → coach returns "" harmlessly — assert this in a test). *Tests:* a trigger fire with a primary-ticker
snapshot includes the coach block; a snapshot without one fires unchanged (no block, no error).

---

## Cross-cutting
- **No auth/permission changes** (security model is network isolation).
- **DRF FK ids exposed as `*_id`**; frontend TS must use `*_id` verbatim.
- **Reuse ledger primitives** (`EmptyState`/`Skeleton`/`Toasts`); verify ledger tokens against config.
- **No new external data sources** in M1 (all read-paths over existing models/services).

## Suggested build order within M1
Coach batch first (one pass over `coach.py`, all backend + cheap): **W6 → W7 → W8 → W5** (W5's regression
test locks in W6–W8). Then the surfacing work: **W1** (track-record endpoint + UI) → **W2** (structured
cards) → **W4** backend aggregator → **W4** tiles + live WS → **W3** capture progress → **W3** `?since=`
(riskiest, last). W1–W4 are independent of the coach batch and can run in parallel subagents; W2/W3/W4 are
frontend-heavy while W5–W8/W1 are backend — good fan-out boundaries.

## Out of scope (deferred to later milestones)
Portfolio "Book" tile content (M4 provides the object; M1 tile can show the ephemeral broker table or a
placeholder until then), fundamentals/analytics tiles (M2), error surface (M3), palette verbs (M5).
**Coach gaps deferred to M6:** coach context on plain chat threads with no snapshot (needs a snapshot-free
"situation" definition) and per-follow-up-turn refresh (interacts with token budget + the eval harness).
The remaining M6 AI-depth items (eval harness, self-critique, calibrated confidence, consensus, richer
schema) stay in M6.
