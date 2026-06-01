# Ledger — launch copy

Ready-to-paste marketing copy for three channels. Each is written to that
platform's length limit and tone, so don't reuse one blurb across all three.
See [`FEATURES.md`](../FEATURES.md) for the full feature sheet.

---

## GitHub

### About description (the repo "About" box — plain text, ~350-char limit)

Primary (front-loads the value in the first ~120 visible chars):

```text
Local-first AI co-analyst for the markets: snapshot the tape, reason with Claude/OpenAI/local models, log your calls, and let deterministic post-mortems grade them — then feed that track record back into the next prompt. Observational only; no broker write path.
```

Shorter alternative (~190 chars):

```text
Local-first AI co-analyst for the markets that grades its own calls: snapshot → reason (Claude/OpenAI/local) → log a thesis → deterministic post-mortem → feed the result back. Observational only.
```

### README header bullets (the three-line pitch)

- 🔁 **Closes the loop:** theses → deterministic post-mortems → a track record that's fed back into every new analysis via the Decision Coach.
- 🧠 **Bring your own AI:** Claude, OpenAI, or any local OpenAI-compatible model — compare them side-by-side, and measure which is actually right with a look-ahead-safe eval harness.
- 🔒 **Local & private:** runs in Docker on `127.0.0.1`, encrypted keys, no telemetry, no broker write path.

### Suggested repo topics

`trading` · `stock-market` · `ai` · `llm` · `claude` · `openai` · `self-hosted` · `local-first` · `finance` · `options` · `django` · `react` · `celery` · `pgvector` · `docker`

### Set it from the CLI (optional)

```bash
gh repo edit --description "Local-first AI co-analyst for the markets that grades its own calls: snapshot → reason (Claude/OpenAI/local) → log a thesis → deterministic post-mortem → feed the result back. Observational only."
gh repo edit --add-topic trading,ai,llm,claude,openai,self-hosted,local-first,finance,options,django,react
```

---

## Show HN

Hacker News renders almost no markdown (blank lines separate paragraphs;
asterisks italicize; bullets show literally). The body below is plain text on
purpose — paste it as-is.

### Title (~80-char limit)

```text
Show HN: Ledger – a local-first AI market analyst that grades its own calls
```

### Body

```text
I built Ledger because every "AI + stocks" tool I tried was a glorified chat box: it would opine on a chart and then forget everything the moment I closed the tab. None of them ever told me whether their last ten calls were any good.

Ledger is a single-user, local-first dashboard (Docker, binds to 127.0.0.1) that closes the loop:

- Capture a point-in-time snapshot of the market — quotes, OHLC, option chains, positions, breadth, news, and server-rendered chart PNGs.
- Hand it to the AI of your choice — Claude, OpenAI, or any local OpenAI-compatible endpoint (Ollama/LM Studio/vLLM) — framed by a trading-style profile and an objective. You can fan the same prompt across several models and compare.
- Record the decision you actually made as a "thesis."
- A scheduled, deterministic post-mortem (no AI involved) computes the real forward return at 7/30/90 days and grades the call correct/incorrect/mixed.
- That track record — plus a diff since the last snapshot and semantic recall over everything you've written — is injected back into the next prompt, so the model reasons from your history instead of a blank slate.

The part I'm most proud of is the offline eval harness: it replays a candidate (model + system prompt) against the frozen snapshots of past theses whose outcomes are already known, and scores its directional calls. It's look-ahead-safe by construction — it feeds the model only what was knowable at the time and never the post-trade coaching context, so you can't accidentally inflate the score by leaking the future. It turns "I think this prompt is better" into a Brier score.

Deliberately observational: there is no broker write path. It cannot place a trade. It's a thinking and record-keeping tool, not an execution engine.

Stack: Django 6 + DRF + Channels (websockets for streaming), Celery, Postgres + pgvector for semantic recall, React 19 + TS. Market data via Schwab or free providers (Alpaca, Tiingo, FRED, SEC EDGAR, and more), so it runs with no brokerage login; everything runs in Docker Compose.

Caveats: single-user, security is network isolation (no app-level auth — don't expose it publicly), and it's a personal project, not investment advice.

Happy to answer questions about the eval design or the snapshot/serialization pipeline.
```

---

## Product Hunt

### Name

```text
Ledger
```

### Tagline (~60-char limit)

```text
The AI market analyst that grades its own calls
```

Alternative:

```text
Local-first AI co-analyst that learns from your trades
```

### Description

```text
Ledger turns any AI — Claude, OpenAI, or a local model — into a market co-analyst with a memory. Capture a point-in-time snapshot of the market, get analysis framed by your own trading style, log the call you made, and let deterministic post-mortems grade it against the tape. Every graded call feeds back into the next analysis, so the AI learns from your track record instead of starting from scratch. Runs entirely on your machine, with your keys encrypted at rest. Observational only — no broker write path.
```

### Maker's first comment

```text
Hey Product Hunt! 👋

I built Ledger to scratch my own itch: I wanted an AI analyst that remembered my past calls and could prove whether it was actually any good — not just a chat box that forgets everything between sessions.

So Ledger closes the loop: snapshot the market → AI analysis (any provider, side-by-side) → you log a thesis → a deterministic post-mortem grades it weeks later → that record is fed back into the next prompt. There's even a look-ahead-safe eval harness that replays models against frozen historical snapshots, so you can measure a prompt or model change with a real score instead of a vibe.

It's fully local (Docker, your machine, your keys encrypted at rest) and strictly observational — it can't place trades. I'd love feedback, especially on the calibration/eval side.

Not investment advice. 🙂
```

### Topics

Fintech · Artificial Intelligence · Developer Tools · Privacy · Investing
