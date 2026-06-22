# Consistency Sentinel — Design

**Written 2026-06-22.** Feature #15. Flag when a new directional call contradicts
the AI's own recent stated view (house view or an open call) and surface it.

## Decisions (brainstormed)
- Sources: `CoverageNote.stance` (current house view) + **open** `AIPrediction`s
  for the ticker. Opposite = bullish↔bearish; neutral never contradicts. (recall
  prose source deferred — noisier.)
- Hook at prediction extraction; notify + an analytics endpoint. Derive on read,
  no new model. "Force reconciliation" = surfacing only in v1.

## 1. Detection — `observer/predictions/services/consistency.py`
`find_contradictions(ticker, direction) -> list[dict]` — return conflicting
sources for a (ticker, direction): the `CoverageNote` when its stance is the
opposite direction, and each open `AIPrediction` for the ticker with the opposite
direction. `[]` for neutral or when nothing opposes. Pure/defensive.
`_opposite(d)`: bullish→bearish, bearish→bullish, else None.

## 2. Hook — extract.py
After a new directional prediction is created, call `find_contradictions`; if any,
`notify(user_id=None, kind="contra", title=f"Inconsistent view: {ticker}",
body="New <dir> <ticker> call contradicts <sources>", link="/scorecard")`.
Best-effort — never breaks extraction.

## 3. Readout — `GET /api/analytics/contradictions/`
List current open predictions whose direction opposes the ticker's CoverageNote
stance: `[{ticker, prediction_direction, stance, prediction_id, predicted_at}]`.
A compact Scorecard "Open contradictions" section.

## 4. Tests
detection (bullish-vs-bearish-note → 1; same/neutral → 0; open-prediction
opposition), extraction fires notify once, endpoint shape + query budget, FE list.

## Out of scope
recall-prose source, blocking reconciliation UI, contradiction history table.
