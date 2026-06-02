# What's next — after M15 "The Strategist" (v1 merged + v2 PR'd)

**Written 2026-06-02.** Pick-up reference for after a context clear. Companion to the
memory notes [[m15-strategist-build]] + [[ws-since-replay-test-stack]] (auto-loaded each
session). M15 grew the M14 *resident analyst* into a top-down + adversarial + autonomous
*strategist*.

## Where things stand

- **M15 v1 — MERGED** (PR #89). 4 new apps, each composing the prior ones:
  - `apps.regime` — F1 Regime engine (5-axis deterministic regime + AI narrative; coach-everywhere; change alerts; `/regime`).
  - `apps.book` — F2 Portfolio Risk X-Ray (union book, correlation clusters, regime-fit, daily `BookSnapshot`; `/book`).
  - `apps.warroom` — F3 War Room (bull/bear/skeptic debate → structured verdict; `/warroom`).
  - `apps.desk` — F4 Anomaly-sweep / The Desk (opt-in detector sweep → investigate → Desk feed; `/desk`).
- **M15 v2 — PR #90 OPEN** (`feat/m15-v2`, base `main`, MERGEABLE, 16 commits, 36 files). Agentic Desk + streaming multi-provider War Room. CI gates pre-verified locally green (full backend 1874 passed; ruff/tsc/eslint clean; frontend v2 6/6).

Spec: `docs/superpowers/specs/2026-06-01-m15-strategist-design.md`.
Plans: `docs/superpowers/plans/2026-06-01-m15-f{1,2,3,4}-*.md` + `…-f{3,4}-v2-*.md`.

---

## 1. Immediate (close out M15)

1. **Merge PR #90** once CI is green. (If CI is red, the most likely spots are the e2e `ui` lane — the 4 new pages may need a11y/visual baselines via `make e2e-visual-update` — or a full-suite cross-app test; the `make check` lane was pre-verified locally.)
2. **After merge, on a live stack:** `docker compose restart worker beat` — worker/beat don't hot-reload, so the new beat tasks (`regime.refresh`, `book.snapshot_daily`, `desk.sweep`) and the new `warroom.run_debate` task won't register until a restart (fresh `up`/CI are fine).
3. **Exercise the features (they ship dark / opt-in):**
   - Configure providers in Settings so the AI surfaces actually run (regime narrative, book synthesis, War Room, Desk investigations all degrade to deterministic/empty with no key).
   - Add a **FRED** key → unlocks the regime **rates axis** (`T10Y2Y` curve inversion); without it that axis is "Unknown" (honest, by design).
   - Configure **>1 provider** → War Room multi-provider voices actually diversify (Claude bull vs GPT bear); else all personas run on the default.
   - Flip opt-in flags when ready (all default **OFF**): `ANOMALY_SWEEP_ENABLED` (Desk auto-sweep), `AUTONOMY_AUTO_EXECUTE` (Desk L3 auto-convene). See §5 for the full flag inventory.
4. **Smoke the beat surfaces:** confirm `regime.refresh` produces a `RegimeReading` and `book.snapshot_daily` a `BookSnapshot` once market data + a provider are present (`POST /api/regime/refresh/`, `POST /api/book/recompute/` to trigger on demand).

## 2. The one deferred v2 piece

- **Live WS token-streaming during a *running* War Room debate.** Today the debate runs
  async (`warroom.run_debate`) and the `/warroom/:id` courtroom renders it **on completion**.
  To stream live: add a `useLiveMessages`-style hook keyed on the warroom `thread_id`,
  subscribing through the existing `WebSocketProvider` + `thread.<id>` channel (the persona
  runs already broadcast tokens there via `run_ai_on_message`). Frontend-only; the backend
  already streams. Small-to-medium.

## 3. Small follow-ups (pluggable onto M15's substrate)

- **"Convene War Room" buttons** on thesis / coverage / book **detail pages.** The API already
  accepts subject ids (`thesis_id`/`coverage_note_id`/`book_snapshot_id` on `/api/warroom/runs/convene/`);
  only the buttons are unwired. Quick frontend win — turns War Room from "/warroom free-prompt only"
  into "debate this specific thesis/stance/book-risk in one click."
- **More Desk detectors** (the registry is pluggable): index-vs-breadth **divergence**, **earnings-proximity**
  (covered name reporting soon w/ stale view — `upcoming_events` + `days_to_earnings`). Add as functions in
  `apps/desk/services/detectors.py` + register in `run_detectors`.
- **Enforce the Desk daily-origination cap.** `DAILY_ORIGINATION_CAP` is defined in `apps/desk/constants.py`
  but not enforced (v1 bounds via top-K + cooldown only). Add a per-day count check in `run_sweep`.
- **Executable "Open thesis"** Desk action (currently a suggestion only) — a prefilled thesis-form deep link.
- **Book X-Ray $-VaR / factor beta** (v1 is conviction-weighted units + correlation clusters; a real
  dollar-risk / beta-to-SPX lens is the natural next depth).

## 4. M16 candidates (next milestone — from the original brainstorm slate + M15 deferrals)

These were surfaced during the M15 brainstorm or its umbrella spec's "deferred" list and remain unbuilt:

- **Expected-move overlay** — options-implied expected move per ticker (you store `OptionChainSnapshot` + IV);
  frame every observation/prediction against "is this move within or beyond what's priced." (Theme-A from the slate.)
- **Playbook / forward scenarios** — pre-committed "if X → then …" branch trees per thesis/ticker, pairing with
  the invalidation criteria you already collect.
- **MCP-out server** — expose coverage / theses / recall / predictions as an MCP server so your *other* AI tools
  (Claude Desktop, this CLI) can ask "what's our house view on NVDA?" Turns the second brain into a knowledge
  source for the whole agent ecosystem. (Most forward-looking; infra-flavored.)
- **Calibration-drift sentinel** — watch the calibration curve over time; alert when the AI (or a provider)
  drifts from well-calibrated to over/under-confident. Reuses `aieval` + `analytics/calibration` + the Mirror.
- **Consistency sentinel** — flag when today's stance contradicts a recent *stated* view across coverage
  revisions / observations / predictions, and force an explicit reconciliation. Reuses `recall`.
- **Themes / narrative tracker** — group tickers into narratives (AI-capex, GLP-1, …), track narrative health
  (breadth of participation, leadership, relative strength); reason at the theme level. (Watchlists are flat today.)

Pick one, run it through `brainstorming → writing-plans → subagent-driven-development` as a new milestone
(new spec + plan per feature). Foundation-first ordering paid off in M15 — keep composing at the seams.

## 5. Opt-in flag + config inventory (all default OFF / unset)

| Flag / config | Effect when on/set |
|---|---|
| `ANOMALY_SWEEP_ENABLED` | Desk auto-sweep beat (`desk.sweep`) actually runs |
| `AUTONOMY_AUTO_EXECUTE` | Desk L3: auto-convene a War Room on high-severity findings |
| FRED API key (Settings → data sources) | Regime **rates axis** (`T10Y2Y`/10Y) |
| ≥2 enabled providers | War Room **multi-provider** voice diversity |
| `AI_INVESTIGATION_MAX_ITERATIONS` | bounds the agentic tool loop (Desk investigation + grounded War Room personas) |
| `AI_AUTONOMOUS_DAILY_CAP_USD` | separate lower daily cap for background/autonomous runs |

## 6. Dev / operational notes (don't relearn these)

- **Worktree test stack** (`ws-since-replay`, no `.env`): self-contained `compose.worktree.yaml` + `docker compose -p ws-since-replay exec -T web pytest …`. File-writing cmds (makemigrations/ruff) need `-u 1000:1000` (+ `-e RUFF_CACHE_DIR=/tmp/ruff` for ruff). Frontend: one-off `docker run … ai-dashboard-frontend … pnpm exec vitest/tsc/lint` with worktree `src` mounted. Full recipe in [[ws-since-replay-test-stack]].
- **Ruff gotcha:** app-scoped `ruff format apps/X` misses test files in *other* apps you touched (dashboard/threads/observer). Always run repo-wide `ruff check .` + `ruff format --check .` before a PR. Migrations are `extend-exclude`d.
- **Push as dan-wiseman94:** `env -u GITHUB_TOKEN git push` (GITHUB_TOKEN → wrong identity → 403). `--no-verify` is fine when suites pass locally (the pre-push hook can mis-resolve worktree paths).
- **CELERY_TASK_ALWAYS_EAGER is per-test** (`@override_settings`), not global — patterns that rely on `.delay()` running inline must set it.
- New Django app or beat task → `INSTALLED_APPS` + `config/urls.py` (before generic `/api/`) + `config/celery.py` explicit `autodiscover_tasks` list + `docker compose restart worker beat`.

## Pointers
- Memory: [[m15-strategist-build]], [[ws-since-replay-test-stack]], [[feedback-autonomous-build-no-push]], [[branch-base-off-origin-main]], [[push-as-dan-wiseman94-github-token]].
- PRs: #89 (v1, merged), #90 (v2, open).
- Branch for v2: `feat/m15-v2`. The isolated `ws-since-replay` Docker stack may still be up.
