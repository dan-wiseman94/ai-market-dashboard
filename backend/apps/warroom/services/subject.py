"""Render a debate subject into a (label, context) pair for the personas."""

from __future__ import annotations


def subject_context(*, thesis=None, coverage_note=None, book_snapshot=None, free_prompt: str = "") -> tuple[str, str]:
    if thesis is not None:
        label = f"Thesis: {thesis.ticker} ({thesis.direction})"
        ctx = (
            f"Debate this thesis.\nTicker: {thesis.ticker}\nDirection: {thesis.direction}\n"
            f"Conviction: {thesis.conviction}/5\nRationale: {thesis.rationale or '(none)'}\n"
            f"Target: {thesis.target_price}  Invalidation: {thesis.invalidation_price}"
        )
        return label, ctx
    if coverage_note is not None:
        label = f"Coverage: {coverage_note.ticker} ({coverage_note.stance})"
        ctx = (
            f"Debate the house view on {coverage_note.ticker}.\nStance: {coverage_note.stance} "
            f"(conviction {coverage_note.conviction}/5)\nBull case: {coverage_note.bull_case or '(none)'}\n"
            f"Bear case: {coverage_note.bear_case or '(none)'}"
        )
        return label, ctx
    if book_snapshot is not None:
        conc = book_snapshot.concentration or {}
        fit = book_snapshot.regime_fit or {}
        label = "Book risk"
        ctx = (
            f"Debate whether the book's risk is a problem.\nConcentration HHI: {conc.get('hhi')}\n"
            f"Net long {conc.get('net_long')} / net short {conc.get('net_short')}\n"
            f"Regime fit: {fit.get('alignment')} — {fit.get('note')}"
        )
        return label, ctx
    label = (free_prompt or "Open question")[:80]
    return label, (free_prompt or "")
