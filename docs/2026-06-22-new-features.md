# New features — 2026-06-22 review-driven batch

Five net-new features built on branch `fix/post-review-batch`, alongside a full
review-remediation fix batch. All ship **dark / opt-in where they spend or notify**,
degrade honestly with no AI key / thin data, and are TDD-covered. Design specs live
under `docs/superpowers/specs/2026-06-22-*`.

## 1. Expected-move overlay
Frame every observation/prediction against what the **options market priced**.
- `apps.market.services.expected_move` computes the 1σ implied move
  (`atm_iv × √(days/365)`, percent-normalized, nearest-expiry) and a 7/30/90-day
  term structure from the stored option chain.
- The snapshot's chain section now feeds the AI an **"Options-implied move (1σ)"** line.
- Each `AIPrediction` freezes `expected_move_pct` at decision time; at resolution the
  Scorecard reports a **"beat-the-straddle"** rate — how often the actual move
  exceeded what was priced, and how often it did so *in the right direction* (edge).
- **Use:** automatic. See it on the chain in any snapshot and on `/scorecard`.

## 2. Calibration-drift sentinel
Watch the AI's calibration over time and alert when a model drifts to over/under-confident.
- `analytics.services.calibration_drift` trends `EvalRun.calibration_error`
  (recent vs prior window), honest `insufficient_history` below min-runs.
- Daily beat task notifies **once per drift episode** (re-arms on recovery).
- **API** `GET /api/analytics/calibration-drift/`; a "Calibration drift" section on `/scorecard`.
- **Opt-in:** `CALIBRATION_DRIFT_SENTINEL_ENABLED=true` (default off; reads only, no AI spend).

## 3. Consistency sentinel
Flag a new directional call that contradicts the AI's own stated view.
- `find_contradictions(ticker, direction)` checks a new call against the
  `CoverageNote` house view and any still-open opposite-direction prediction.
- Notifies (`contra`) at prediction extraction; **API** `GET /api/analytics/contradictions/`
  lists open calls that oppose the house view; an "Open contradictions" section on `/scorecard`.
- **Use:** automatic on prediction extraction.

## 4. Themes / narrative tracker
Group tickers into narratives (AI-capex, GLP-1, …) and read each narrative's health.
- `apps.market.Theme` (name + tickers) + `services/themes.theme_health`:
  **breadth** (participation), **leadership** (leader/laggard), and **relative strength**
  vs `$SPX`, from split-corrected OHLC returns; honest coverage below 2 priced members.
- **API** `ThemeViewSet` at `/api/themes/` (CRUD) + `GET /api/themes/<id>/health/`.
- **UI:** a new **`/themes`** page (SideNav → *Themes*) — create a narrative, see its health.

## 5. MCP-out server
Expose the second brain to **external agents** (Claude Desktop, this CLI) as MCP tools.
- Dependency-free JSON-RPC 2.0 at **`POST /api/mcp/`** (`initialize` / `tools/list` /
  `tools/call`). Four read-only tools: `house_view`, `theses`, `predictions`, `recall_search`.
- **Auth:** opt-in shared token — set `MCP_AUTH_TOKEN` (clients send
  `Authorization: Bearer <token>`) before exposing beyond localhost; unset keeps the
  app's 127.0.0.1 posture.

## Already present (verified, not rebuilt)
The review's roadmap was stale in the codebase's favor — these were already shipped:
**Book X-Ray $-VaR / factor-beta** (`/book`), **coach on snapshot-free chat**, and the
**War Room live-stream + Convene buttons**.

## Fix batch (same branch)
Alongside the features: the review's correctness fixes — Polygon split-math, Files-API
documents reaching the model, a working `make restore`, Claude cache-token billing,
retention-`0` data-loss guard, a true pct_change sliding window, a race-free stop, ops
hardening (`.dockerignore`/restart/pinned node), and frontend resilience + threads
pagination. See the PR for the full commit list.
