# Decision Coach (stateful context + track record) — design

**Date:** 2026-05-29
**Status:** Approved (pending spec review)
**Topic:** Make the AI **stateful and self-calibrating by default**. Today every observation starts from zero — no memory of prior looks, no awareness of what changed, no knowledge of the trader's own track record, and not even the current date. The machinery to fix this (semantic recall, snapshot diff, thesis/post-mortem outcomes, calibration) already exists on this branch but was each built for its own surface and never wired into the prompt the model actually runs on. This spec composes those existing pieces into the generation path. Scope = Layers 1+2 (stateful context + track record); typed-output and a bias-mirror UI are explicitly deferred.

## Problem

The audit found — and we verified in code — that the AI is stateless and the learning loop is open:

- **No system prompt beyond `profile.style`.** `apps/threads/_request.py:132` sets `system = thread.profile.style if thread.profile else ""`. There is no observational framing and, critically, **the model is never told the current date/time**, so it cannot correctly reason about "earnings in 3d" or "news in the last 24h."
- **No memory across sessions.** `_history_messages` (`_request.py:76`) pulls *same-thread* turns only, so a fresh capture-and-ask thread begins with total amnesia. Semantic recall (`apps/recall/services/search.py`) exists but is reachable only as an opt-in tool and via the `/recall` page — never auto-injected.
- **"What changed since last look" is computed but never shown to the model on the main path.** `previous_snapshot_for` + `diff_sections` (`apps/snapshots/primary.py`, `apps/snapshots/diff.py`) power the snapshots browser and the observer's opt-in diff mode, but the default snapshot→AI run never sees a diff.
- **The loop is open.** A grep for `forward_return | objective_verdict | calibration | price_path` across `apps/threads`, `apps/briefing/services`, `apps/observer/services`, and `apps/snapshots` returns nothing. Forward returns and post-mortem verdicts are computed (`apps/thesis`, `apps/market/returns.py`) and aggregated into a scorecard (`apps/analytics/services/calibration.py`), but the model that made the calls **never sees its own hit-rate**, so it cannot hedge, adjust confidence, or stop repeating a losing pattern.

The substrate is unusually complete. This is a **wire-and-synthesize** feature, not a build-from-scratch.

## Non-goals (YAGNI)

- **No typed `ObservationReport` on the default path.** Emitting structured signals (confidence + invalidation) on snapshot runs and feeding them back into calibration is Layer 3 — a future spec.
- **No bias-mirror analytic or decision-time UI banner.** Overconfidence detection and a visible track-record card at thesis-creation are Layer 3.
- **`explain-diff` is unchanged.** It is already a focused "what changed" surface with its own diff context; adding the Coach block would be redundant.
- **No new frontend surface.** The Coach block rides inside the existing synthetic snapshot user-message and renders in the current collapsible message view — no new component, route, or endpoint. The only frontend touch is the `enable_coach` checkbox joining the existing profile-settings form.
- **The morning briefing's assembler is unchanged** (no Coach block added). Like every AI run, briefing calls *do* pick up the new base system prompt via `_build_request` — that is intended, not a regression.
- **No GPT-5 reasoning / structured-output wiring, no temperature changes.** Separate AI-quality items, out of scope here.
- **No new external data, dependency, credential, Celery task, or beat entry.**

## Design decisions (settled during brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| MVP scope | Layers 1+2: stateful context **+** track record | The core "remembers and self-calibrates" coach; feasible in one spec because the substrate is built |
| Default state | **Default-on**, with a per-profile kill switch (`enable_coach`, default `True`) | Opt-in-and-off is exactly why recall/tools/thinking sit idle; the point is to make the AI stateful *by default* |
| Where each context lives | **Hybrid**: stable framing → system prompt (cached); volatile context → visible synthetic user turn | Volatile data in the system block would bust the cache every run and be invisible; framing-as-user-turn is less authoritative |
| Injection locus | One assembler helper, called at the **2 snapshot-message creation sites**; base prompt in `_build_request` | Persisted ⇒ visible in the thread (trust for a default-on feature); only on the snapshot turn ⇒ no re-injection/staleness on follow-ups |
| Recall source | `related_to_ticker` (pure DB, recency-ordered) | Never touches the embedding service ⇒ can't fail on it; cheap and robust |
| Track record | New deterministic `track_record_for_ticker` (no AI), min-n gated | Mirrors the rest of the calibration machinery (no key needed); honest about thin history |
| Bounding | Hard item caps (≤3 theses, ≤5 recall, diff already top-N, ≤2 track lines) | Block ≈1–1.5k tokens by construction; the snapshot payload stays independently pruned |
| Failure mode | Assembler **never raises**; each sub-section isolated; top-level guard ⇒ `""` | It is default-on in the hot path — a Coach bug must cost context, never the capture-and-ask |

## Architecture

```
 run that reasons over a snapshot
        │
        ├── system prompt ──────────────────────────────────────────────┐
        │     _build_request (apps/threads/_request.py)                  │
        │       system = build_system_prompt(profile, now)               │  STABLE → RunRequest.system (cached)
        │       = observational framing + "today is <ET date/session>"   │
        │         + "## Your trading style\n{profile.style}"             │
        │       (enable_coach=False ⇒ just profile.style — status quo)   │
        │                                                                ▼
        └── user turn (synthetic snapshot Message, persisted ⇒ visible) ─┐
              created at 2 sites:                                        │  VOLATILE → message content["text"]
                • ThreadViewSet.create  (pinned snapshot)                │
                • observer/services/run.py  (per fire)                   │
              content["text"] = assemble_coach_context(snap, profile)    │
                                 + serialize_for_ai(snap)                │
                                                                         ▼
              assemble_coach_context (apps/threads/coach.py, lazy imports):
                ├─ Open theses on snap.primary_ticker     (apps.thesis)        ≤3
                ├─ Since your last look: diff_sections(prev, curr)             (apps.snapshots)  top-N
                │     prev = previous_snapshot_for(snap)                       (omit if none)
                ├─ Your track record: track_record_for_ticker(...)            (apps.analytics)  min-n gated
                └─ You've noted this before: related_to_ticker(ticker, k=5)   (apps.recall)     ≤5
              (any sub-section that errors or is empty is omitted; all-empty ⇒ "")
```

### 1. Profile kill switch — `apps/profiles/`

Add one field to `TradingProfile` (`apps/profiles/models.py`):

```python
enable_coach = models.BooleanField(default=True)
```

- Default `True` ⇒ existing profiles get the Coach on (the "default-on" decision); the field default covers existing rows, so **no data migration** is needed.
- `enable_coach=False` ⇒ **exact status-quo behavior**: `system = profile.style`, no context block. One switch reverts everything.
- Expose it in the profile serializer (`apps/profiles/serializers.py`, read/write) so the kill switch is reachable from the existing profile settings UI. (No new UI component — it joins the existing `enable_tools` / `enable_thinking` / `enable_memory` toggles.)

### 2. Base system prompt — `apps/threads/coach.py` (new)

```python
def build_system_prompt(profile, *, now) -> str:
    """Stable framing + current ET date/session, wrapping the profile style.

    Returns just `profile.style` (today's behavior) when profile is None or
    enable_coach is False. Pure function: no cross-app imports, never raises.
    """
```

- Renders `now` in `America/New_York` (the app's ET convention) as a date + weekday + time line, plus a best-effort market-session phrase ("US equity markets are OPEN/CLOSED"). The session lookup is wrapped — if the calendar helper is unavailable it degrades to a date-only line.
- Framing text (verbatim target):

  ```
  You are a market-observation assistant for one experienced trader.
  Today is <Weekday YYYY-MM-DD, HH:MM ET>; US equity markets are <OPEN|CLOSED>.

  Your role is strictly observational: describe what the data shows, surface what's
  notable, reason about scenarios. Do NOT issue buy/sell/hold directives.

  Ground every claim in the specific data you were given and name which section it
  came from. Explicitly flag data that is missing, stale, or pruned. Quantify your
  confidence and state what would invalidate your read.

  ## Your trading style
  {profile.style}
  ```

- Called from `_build_request` (`apps/threads/_request.py:132`): `system = build_system_prompt(thread.profile, now=timezone.now())`. Applies to **all** runs (snapshot or not); cached via the existing `cache_system=True`.

### 3. Volatile Coach block — `apps/threads/coach.py`

```python
def assemble_coach_context(snapshot, profile) -> str:
    """Compose the 'what you already know' block for a snapshot-bearing run.

    Returns "" when profile.enable_coach is False, when there is no primary_ticker,
    or when every sub-section is empty. NEVER raises (see §6). Cross-app reads
    (thesis/recall/analytics/snapshots) use lazy, function-local imports to respect
    the documented threads -> thesis import-cycle constraint.
    """
```

The block opens with a heading — `## 🧭 What you already know  (auto-assembled context — may be incomplete)` — followed by these sub-sections (each independently `_safe`-wrapped), in order, with `ticker = snapshot.primary_ticker`:

1. **Open theses on `{ticker}`** — `Thesis.objects.filter(ticker=ticker, status="open").order_by("-conviction", "-opened_at")[:3]`. Per thesis: direction, conviction, entry/target/invalidation, age, and price-vs-target/invalidation computed from the snapshot's own `quotes` section `last` (no extra fetch). Omitted if none.
2. **Since your last look** — `prev = previous_snapshot_for(snapshot)`; if present, `diff_sections({kind: payload} prev, {kind: payload} curr)` (the same `{kind: payload}` dict shape the `explain-diff` endpoint builds). The diff is already top-N capped internally. Omitted if no prior ready snapshot for this ticker.
3. **Your track record here** — `track_record_for_ticker(ticker, direction=<open thesis dir, if any>, conviction=<open thesis conviction, if any>)` (see §4). Omitted (or "insufficient history") below min-n.
4. **You've noted this before** — `related_to_ticker(ticker, k=5)` (recency-ordered, pure DB). Each hit: source date, kind, 280-char snippet (already capped in `_hit`), and link. Omitted if none.

Block bound ≈1–1.5k tokens by construction. It is deliberately **not** a prune candidate (it is the high-value context); its item caps are the tuning knob if budget ever bites. The snapshot payload continues to be pruned by `serialize_for_ai` independently.

### 4. Per-ticker track record — `apps/analytics/services/calibration.py`

```python
def track_record_for_ticker(ticker, *, direction=None, conviction=None, min_n=3) -> dict | None:
    """Deterministic (no AI) track record for one ticker, plus an optional
    direction/conviction slice over all history. Returns None when total decisive
    history is below min_n, so the caller omits the sub-section honestly."""
```

- **Per-ticker:** closed theses on `ticker` (`Thesis.objects.filter(ticker=ticker).exclude(status="open")`) summarized as win/loss/scratch/invalidated counts, plus decisive hit-rate from their `PostMortem` verdicts; include the most recent closed thesis as a one-liner.
- **Slice:** when `direction`/`conviction` are supplied (borrowed from the live open thesis so the line is relevant), count decisive `PostMortem`s whose thesis matches that direction+conviction across all history → "your conviction-{c} {direction} calls: x/y correct (z%)".
- Reuses `_hit_rate`, `_DECISIVE`, and the `PostMortem ⋈ Thesis` query pattern already in this module. Min-n gate keeps small samples from masquerading as signal (consistent with the leaderboard's `coverage_pct`/`None` discipline).

### 5. Call-site integration

- **`apps/threads/_request.py`** — `_build_request`: swap the bare `system = ...style` for `build_system_prompt(...)` (§2). One line.
- **`apps/threads/views.py`** — `ThreadViewSet.create` (pinned-snapshot path): `content["text"] = assemble_coach_context(snap, profile) + serialize_for_ai(snap)` instead of `serialize_for_ai(snap)` alone. The block is empty-string when gated/empty, so the message is byte-identical to today in that case.
- **`apps/observer/services/run.py`** — per-fire synthetic message: same prepend.
- The block lives only on these snapshot-creation messages, so **follow-up turns stay clean** (no re-injection).

### 6. Error handling & degradation

`assemble_coach_context` mirrors the briefing assembler's `_safe` pattern (`apps/briefing/services/assemble.py`) and the post-mortem narrative's degrade-to-`{}`:

- Each sub-section is wrapped so a failing source (DB hiccup, malformed payload) yields an **omitted sub-section**, never a broken run.
- A top-level guard returns `""` and logs on any unexpected error. A Coach defect can therefore only ever cost context, never the capture-and-ask. This matters because the feature is default-on in the hot path.
- `related_to_ticker` (not `search`) is used precisely so recall here never depends on the embedding service. `diff_sections` already carries a never-raises invariant.
- `build_system_prompt` is pure and trivial; the session lookup is best-effort.

### 7. Testing (favoring `pytest.mark.parametrize`)

- **`apps/threads/tests/test_coach.py`**
  - `build_system_prompt`: includes ET date + session + observational framing + wraps `style`; `enable_coach=False` ⇒ returns exactly `profile.style`; `profile=None` ⇒ `""`.
  - `assemble_coach_context`: parametrized over present/absent open theses, present/absent prior snapshot (diff present/absent), present/absent recall hits, min-n-gated vs populated track record, `enable_coach=False` ⇒ `""`, all-empty ⇒ `""`.
  - **Never-raises invariant:** monkeypatch each sub-source to raise → block still returns with that section dropped; nothing propagates.
  - Caps enforced (≤3 theses, ≤5 recall).
- **`apps/analytics/tests/test_calibration.py`** (extend): `track_record_for_ticker` — per-ticker closed-thesis aggregation, the direction/conviction slice, min-n gating, the no-post-mortem case, hit-rate math.
- **Integration** (`apps/threads/tests/test_request.py` / task test): `_build_request` sets the base prompt when `enable_coach` (status quo when off); a pinned-snapshot thread's **first** user message contains the 🧭 block while a **follow-up** turn does not; an observer fire includes the block.
- **Budget regression:** a snapshot run still serializes within `max_payload_tokens` with the block present.
- **E2E:** optional, not a gate (mock fixtures lack real history) — do not manufacture scope.

### 8. Migration & ops

- One reversible migration in `apps/profiles/migrations/`: `AddField TradingProfile.enable_coach` (`BooleanField(default=True)`, reversible `RemoveField`). No data migration (the default covers existing rows). No locking concern at single-user scale.
- **No new Celery task or beat entry ⇒ no `worker`/`beat` restart needed.**
- No new dependency, credential, or external service.
- Honors the repo's silent-failure landmines: reads `Snapshot.status="ready"` (via `previous_snapshot_for`) and section `status="done"` correctly; no direct provider instantiation; no secret logging; lazy cross-app imports for the threads→thesis cycle.

## Implementation order (for the plan)

1. `TradingProfile.enable_coach` field + migration; expose in `ProfileSerializer`; serializer/model tests.
2. `apps/threads/coach.py` → `build_system_prompt` (pure) + unit tests; wire into `_build_request` (§5) + request test (status quo when off).
3. `track_record_for_ticker` in `apps/analytics/services/calibration.py` + tests.
4. `apps/threads/coach.py` → `assemble_coach_context` (all four sub-sections, caps, lazy imports, `_safe` wrapping) + parametrized tests incl. never-raises invariant.
5. Prepend at the two creation sites (`ThreadViewSet.create`, `observer/services/run.py`) + integration tests (first-turn-only, observer-includes, budget regression).

Steps 2–4 are independent of each other and can be built in parallel; step 5 depends on 2+4 (and 3 via 4). Each step is independently testable and shippable.
