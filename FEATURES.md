# Ledger

**The AI co-analyst for the markets that actually *learns* from your calls.**

Ledger captures a rich, point-in-time picture of the market, hands it to the AI of
your choice for analysis framed by *your* trading style — then closes the loop:
you record the decision you made, and Ledger grades it against the tape weeks
later. Every graded call feeds back into the next conversation, so the model stops
reasoning from a blank slate and starts reasoning from *your history*.

**Runs entirely on your own machine. Strictly observational — it reads the market and reasons about it, and never places a trade.**

---

## Why Ledger is different

Most "AI + markets" tools stop at *"here's a chart, ask a chatbot."* Ledger is built
around a complete, closing feedback loop:

```text
   Capture            Reason              Decide             Grade              Learn
 ┌──────────┐      ┌──────────┐       ┌──────────┐      ┌───────────┐      ┌──────────┐
 │ Snapshot │  →   │  AI obs. │   →   │  Thesis  │  →   │ Post-     │  →   │  Coach + │
 │ the tape │      │ (3 AIs)  │       │ + journal│      │ mortem    │      │  recall  │
 └──────────┘      └──────────┘       └──────────┘      └───────────┘      └────┬─────┘
       ▲                                                                         │
       └─────────────────────  feeds the next prompt  ◄──────────────────────────┘
```

- **🔁 A learning loop, not a chatbot.** Your past theses, win/loss record, and the
  diff since the last snapshot are auto-injected into every new analysis. The AI
  remembers what you've done and how it turned out.
- **⚖️ It grades itself — honestly.** Deterministic post-mortems score every call
  against real forward returns with **no AI required**. A separate offline harness
  replays candidate models against *frozen* historical snapshots to measure whether
  the AI is actually any good — and it's **look-ahead-safe by construction** (it
  never lets post-trade information leak back into the score).
- **🧠 Bring your own brain.** Claude, OpenAI, or any local OpenAI-compatible model
  (Ollama, LM Studio, vLLM, llama.cpp) — switch freely, or run the *same* prompt
  across several at once and compare side-by-side.
- **🔒 Local-first and private.** Everything runs in Docker on `127.0.0.1`. No
  cloud account, no telemetry, no data leaving your machine except the AI calls
  *you* configure. Your API keys are encrypted at rest.
- **🛡️ Safe by design.** No broker write path. Ledger cannot place, modify, or
  cancel an order. It's a thinking tool, not an execution engine.

---

## What's inside

### 📸 Market capture & snapshots

- **Point-in-time snapshots** of the whole picture, from opt-in sections: live
  **quotes**, **OHLC history**, **option chains**, **positions**, **market
  breadth**, **news**, **macro indicators**, **SEC filings**, **Treasury rates**,
  **rendered chart images** (real PNGs from a headless browser), and a
  **forward earnings/macro calendar**.
- **Free data sources, no brokerage required.** Add a free-tier key (Alpaca,
  Tiingo, Twelve Data, Polygon, Tradier, FRED, Marketaux) under Settings →
  Connections and the quotes / OHLC / option-chain / news pipeline falls back to it when
  Schwab isn't connected — plus keyless **SEC EDGAR** filings and **US Treasury**
  rates. The whole dashboard runs without a Schwab login.
- **Nothing is silently dropped.** If a section fails, it's flagged in the payload
  so the AI knows exactly what it couldn't see — partial captures are honest, not misleading.
- **Overnight / pre-market mode** adds index, vol & rates **futures**, overseas
  quotes, extended-hours bars, and overnight news — with per-ticker gap % vs. the prior close.
- **Objective + style framing** on every capture: tell the model *what* you're
  asking and *how* to look at it.
- **Snapshot diffs** — get a clean markdown delta between any two captures.

### 🤖 Bring-your-own-AI

- **Three backends, one experience** — Claude (Anthropic), OpenAI, and any local
  OpenAI-compatible endpoint. Cost is hard-zeroed for local models.
- **Trading-style profiles** — reusable AI personas that frame the analysis and
  toggle advanced capabilities per profile.
- **Smart routing & budgeting** — per-model pricing and context budgets are built
  in; payloads are automatically trimmed to fit each model before they're sent.

### 💬 Conversations & multi-model compare

- **Live token streaming** over WebSockets — watch the analysis appear in real time.
- **Compare mode** — fan the *same* prompt across multiple provider+model pairs in
  parallel, each in its own branch tab. See who's right before you decide.
- **True stop** — halting a stream aborts the upstream generation *and* the billing,
  not just the on-screen text.
- **Pinned snapshots** — the exact market picture the AI saw is recorded as the
  first turn, so you (and it) always have the full context.

### 🧩 Advanced AI capabilities (opt-in per profile)

- **Tool use on all three providers** — an agentic tool loop with a pluggable
  registry; every tool call is recorded and streamed live.
- **Extended thinking** *(Claude)* — budgeted step-by-step reasoning.
- **Persistent memory** *(Claude)* — a per-profile memory directory the model can read & write.
- **File attachments & citations** *(Claude)* — upload documents; news is sent as
  citable sources the UI links back to.
- **Prompt caching** *(Claude)* — multi-turn chats reuse cached context at a fraction of the cost.
- **No silent failures** — ask for a capability a provider can't honor and Ledger
  shows a visible warning, then continues with what it *can* do.

### 🎓 Decision Coach & semantic recall — the "second brain," wired in

- **Decision Coach** — before each analysis, Ledger assembles a *"what you already
  know"* briefing and injects it into the prompt: your open theses on the ticker
  (conviction, entry/target/invalidation with % distance), the diff since the last
  snapshot, your **per-ticker track record** (win/loss, hit-rate by conviction),
  **setup-cohort base rates** (how calls like this one have resolved — the outside
  view), **distilled lessons** from your past trades, and the most relevant things
  you've written before.
- **Semantic recall** — search across *everything* — messages, snapshots, theses,
  journal entries, observations, and post-mortems — with embedding-based similarity
  (pgvector) and a keyword fallback. Find that thing you noticed three months ago in seconds.

### 📓 The second brain — theses, post-mortems & decision journal

- **Theses** — record a directional call: direction, rationale, conviction (1–5),
  optional entry/target/invalidation, and a horizon. Linked to the thread and snapshot that sparked it.
- **Deterministic post-mortems** — at 7, 30, and 90 days, Ledger computes the real
  forward return from stored price history and assigns an **objective verdict**
  (correct / incorrect / mixed / inconclusive) — *no AI key needed, no hindsight bias*.
- **AI narrative review** *(best-effort)* — when available, a structured "what
  worked / what was missed / lessons / would-you-repeat" report lands in a per-thesis review thread.
- **Decision journal** — log what you actually did (acted / passed / watching /
  hedged) and why, so your reasoning is captured even when you do nothing.
- **Agent presets** — ready-made analysis modes (earnings prep, devil's advocate,
  pre-trade bias check, triage pass) that pre-fill the composer.

### 🔮 Prediction Ledger — the AI's own calls, graded

- **The AI goes on the record.** Every structured observation that carries a
  directional call becomes a first-class **prediction** — direction, confidence, an
  invalidation level, and a horizon — extracted automatically at no extra cost.
- **Graded by the tape, not by vibes.** At horizon end the real forward return is
  computed from stored history and the call is scored correct / incorrect / mixed,
  deterministically and with no AI. You get an **invalidation alert** the moment a
  live call is being proven wrong, before its horizon is even up.
- **Beat the straddle.** Every observation is also framed against what the *options market priced* — the 1σ implied move read from the chain — and each prediction freezes that expected move at decision time, so the scorecard can report how often the actual move beat the straddle, and how often it did so in the right direction.
- **Is your AI actually any good?** The scorecard shows the AI's live hit-rate by
  confidence band and Brier score, per provider and model — its own track record, measured.
- **A second opinion at decision time.** Open a thesis and see whether the AI
  currently agrees or diverges on that ticker.

### 🔬 Eval-driven calibration — *measure* whether the AI is good

- **Offline evaluation harness** replays a candidate model + system prompt against
  the **frozen** historical snapshots of decisive past theses and scores its
  directional calls — turning "I think this prompt is better" into a number.
- **Look-ahead-safe by construction** — it feeds the model only what was knowable at
  the time, never post-trade context, so scores can't be inflated by leakage.
- **Closes the loop in production** — the latest eval result (measured hit-rate,
  Brier score, and an over/under/well-confident verdict) is fed straight back into
  the live Decision Coach.

### 🧭 The Resident Analyst

The AI stops being a one-shot snapshot reader and starts behaving like an analyst on retainer.

- **Autonomous investigation** — a trigger or schedule can set the AI loose on a
  *bounded* tool-backed investigation — pulling data and following leads to a
  grounded conclusion — instead of a single static observation. Iteration- and
  spend-capped; opt-in per trigger/schedule.
- **It routes itself by track record** — turn it on and the AI fallback picks the
  best-*measured* model from your eval history rather than whichever was configured
  first. The more accurate model earns more of your runs.
- **It learns recurring lessons** — themes from your past trades are clustered and
  labeled by sector and direction, then surfaced cross-ticker in the Coach ("you've
  been too bullish on biotech"), so a lesson from one name informs a brand-new one.
- **The Mirror** — the calibration engine turned on *you*: graded patterns in your
  own decisions ("you pass on winners," "high conviction isn't actually more
  accurate"), each with the evidence — and an honest "insufficient history" when the
  sample is too thin to call.
- **A living house view** — each ticker you cover gets one persistent, version-
  controlled research note (stance, conviction, bull/bear case, key levels) that the
  AI **revises with a reason** instead of re-deriving it every snapshot, with an
  append-only history of *why* the view moved. Browse it at `/coverage/:ticker`.

### 🧭 The Strategist

Where the Resident Analyst works one name at a time, the Strategist steps back to
the whole book and the market regime — and convenes a structured debate before you commit.

- **Market regime** — an append-only series of market-regime reads (several axes
  collapsed into a composite), refreshed on a schedule; the latest row is the
  current read the Coach and the Desk key off.
- **Book risk X-ray** — a daily whole-book risk reading: concentration (HHI),
  correlation clusters over stored price history, names near invalidation, regime
  fit, and a dollar Value-at-Risk + factor-beta-to-`$SPX` lens.
- **War Room** — convene a multi-agent "courtroom" debate (bull / bear / skeptic)
  on a thesis, coverage note, or book snapshot with one click; each persona streams
  live over its thread and the run resolves to a verdict.
- **The Desk** — an agentic anomaly sweep that runs detectors (price, options,
  breadth divergence, earnings proximity, regime change, book deterioration, stale
  coverage), investigates the top findings under a daily cap, and offers one-click
  follow-ups: convene a war room, revise coverage, or open a prefilled thesis.

### 📊 Calibration scorecard & analytics (on-demand)

- **Calibration scorecard** — are you *actually* more right when you're more
  confident? Hit-rate per conviction bucket and a Brier score, by direction, plus
  per-(provider, model) calibration. Click any bucket to drill into the theses behind it.
- **Provider leaderboard** — which AI's calls actually correlate with forward
  returns, with an honest coverage figure when price history is thin.
- **Unusual-options detector** — flags chain lines on volume/OI or IV outliers and
  tells you *why* each was flagged. A reasoning surface, not just a scanner.
- **Calibration-drift sentinel** *(opt-in)* — trends each model's calibration error over time and notifies once when it drifts to over- or under-confident, re-arming on recovery (reads eval history only — no AI spend).
- **Consistency sentinel** — flags any new directional call that contradicts the AI's own house view or an open opposite-direction prediction, the moment it's made.
- **Cost-per-insight, trigger heatmap, and observer timeline** round out the picture.

### ⏰ Observer — scheduled AI runs

- **Cron-driven analysis** on your watchlists, in your timezone, market-hours aware
  (NYSE holidays & half-days correct).
- **Three cost-saving modes** — structured typed reports, *diff-only* (feed the AI
  just what changed), and *batch* (~50% cheaper via the Anthropic Batch API).
- **Timeline view** of every run, with push notifications on completion or error.

### 🎯 Event triggers

- **Condition builder** — compose price, %-change, volume, P&L, VIX, and
  days-to-earnings rules with `all` / `any` / `not` logic.
- **Backtest before you arm it** — replay any condition over stored history and see
  exactly when it would have fired.
- **Fires into analysis** — a trip captures a fresh snapshot and notifies you.

### 🌅 Morning Briefing

- **A daily hybrid synthesis** — open theses with price-vs-target, upcoming
  earnings & macro, overnight trigger firings, overnight news, and market breadth,
  optionally synthesized by the AI into a single read.
- **Once-a-day and reliable** — fires automatically past your send time; every
  section degrades gracefully so the briefing always renders, even with no AI key.

### 📅 Forward calendar, themes, portfolio & command centre

- **Forward calendar** — upcoming earnings (with estimates) and curated US macro
  events (FOMC / CPI / NFP / PCE / GDP), surfaced in snapshots, triggers, and its own page.
- **Portfolio** — lightweight manual position tracking with realized P&L, linkable to the thesis behind each trade.
- **Narrative themes** — group tickers into a narrative (AI-capex, GLP-1, …) and read its health: breadth (participation), leadership (leader vs laggard), and relative strength vs `$SPX`, from split-corrected returns, with honest coverage below two priced members. Browse it on its own page.
- **Command-centre dashboard** — the day's tape at a glance, every panel
  fault-isolated so one slow data source never breaks the page.

### 💰 Cost governance

- **Every token accounted for** — aggregation per provider, per model, and per thread.
- **Daily & monthly spend caps** (opt-in) enforced across chats, observers, and triggers.
- **CSV export** and a **per-snapshot cost drill-down** that attributes spend down to each captured section.

### ⚙️ Operations & everyday UX

- **Automated backups** — scheduled database dumps with rotation and one-command restore.
- **Full data export** — async zip bundles of your threads, snapshots, observations, triggers, profiles, and watchlists. Your data is yours.
- **MCP server** *(opt-in)* — expose your second brain (house view, theses, predictions, semantic recall) to external agents like Claude Desktop over a read-only JSON-RPC endpoint at `/api/mcp/`, shared-token-gated before you reach past localhost.
- **Built for speed** — a **command palette** (`⌘/Ctrl-K`) and `g`-then-key
  shortcuts jump to any screen instantly; a polished app shell with breadcrumbs,
  notifications, and a live connection indicator.

---

## Who it's for

- **The self-directed trader / investor** who wants a tireless analyst that frames
  the market in their own style — and keeps them honest with a graded track record.
- **The quietly skeptical** who don't trust AI hype and want to *measure* whether
  the model's calls actually beat a coin flip before relying on them.
- **The privacy-conscious** who want their market thinking to live on their own
  hardware, with the option to run a fully local model and send nothing to the cloud.
- **The tinkerer** who wants to A/B their prompts and models against real, labeled
  history instead of vibes.

---

## Privacy & safety, up front

- **Local-first.** Runs in Docker, bound to `127.0.0.1`. No accounts, no telemetry, no SaaS.
- **Observational only.** There is no broker write path. Ledger cannot trade.
- **Your keys, encrypted.** Provider API keys and brokerage OAuth tokens are
  encrypted at rest; keys are entered in-app, never committed to config.
- **Honest about itself.** Failed data sections, unsupported AI features, and
  thin-coverage analytics are surfaced, not hidden.

> Single-user by design: security is network isolation, so run it on your own
> machine and don't expose it publicly without adding authentication.

---

## Status

**Feature-complete** — market data + snapshots, streaming AI threads, observers +
triggers, the second brain, free data sources, the Prediction Ledger, the Morning
Briefing, the Resident Analyst, the Strategist, expected-move grading, the
calibration-drift and consistency sentinels, narrative themes, and an MCP server.

*One person. One machine. Every call on the record.*
