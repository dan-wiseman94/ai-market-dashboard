"""Decision Coach: a base observational system prompt + an auto-assembled,
stateful "what you already know" context block.

`build_system_prompt` is pure (profile + clock). `assemble_coach_context`
(added in a later task) composes prior theses / diff-vs-last / track record /
recall and uses LAZY, function-local cross-app imports so importing this module
from `apps.threads` never triggers the documented threads -> thesis cycle.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

log = logging.getLogger(__name__)

_BASE_FRAMING = (
    "You are a market-observation assistant for one experienced trader.\n"
    "{when}\n\n"
    "Your role is strictly observational: describe what the data shows, surface "
    "what's notable, reason about scenarios. Do NOT issue buy/sell/hold directives.\n\n"
    "Ground every claim in the specific data you were given and name which section "
    "it came from. Explicitly flag data that is missing, stale, or pruned. Quantify "
    "your confidence and state what would invalidate your read."
)


def _when_line(now: datetime) -> str:
    """'Today is <local date/time>; US equity markets are OPEN|CLOSED.'

    Localized to OBSERVER_BEAT_TIMEZONE (the repo's display-tz convention).
    Entirely best-effort: any failure (bad tz setting, calendar error) degrades
    to a date-only line so build_system_prompt never raises.
    """
    try:
        tz = ZoneInfo(getattr(settings, "OBSERVER_BEAT_TIMEZONE", "UTC") or "UTC")
        stamp = now.astimezone(tz).strftime("%A %Y-%m-%d, %H:%M %Z")
        from apps.market.calendar.sessions import market_state

        st = market_state(market="us_equity", at=now)
        return f"Today is {stamp}; US equity markets are {'OPEN' if st.is_open else 'CLOSED'}."
    except Exception:
        log.warning("coach.session_lookup_failed", exc_info=True)
        return f"Today is {now.strftime('%Y-%m-%d')}."


def build_system_prompt(profile, *, now: datetime) -> str:
    """Base framing + current date/session, wrapping `profile.style`.

    Returns just `profile.style` (legacy behavior) when `profile` is None or
    `enable_coach` is False. Never raises.
    """
    style = (getattr(profile, "style", "") or "") if profile is not None else ""
    if profile is None or not getattr(profile, "enable_coach", False):
        return style
    framing = _BASE_FRAMING.format(when=_when_line(now))
    if style.strip():
        return f"{framing}\n\n## Your trading style\n{style}"
    return framing


def _safe(fn, default: str = "") -> str:
    try:
        return fn() or default
    except Exception:
        log.warning("coach.section_failed", exc_info=True)
        return default


def _fmt_num(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):g}"
    except (TypeError, ValueError):
        return str(v)


def _snapshot_last(snapshot, ticker: str):
    """Primary-ticker last price from the snapshot's own quotes section (no fetch)."""
    for sec in snapshot.sections.all():
        if sec.kind == "quotes" and isinstance(sec.payload, dict):
            row = sec.payload.get(ticker)
            if isinstance(row, dict):
                return row.get("last")
    return None


def _theses_block(ticker: str, snapshot) -> str:
    from apps.thesis.models import Thesis

    theses = list(
        Thesis.objects.filter(ticker=ticker, status="open").order_by("-conviction", "-opened_at")[:3]
    )
    if not theses:
        return ""
    last = _snapshot_last(snapshot, ticker)
    lines = [f"### Open theses on {ticker}"]
    for t in theses:
        bits = [f'[{t.direction} · conviction {t.conviction}/5] "{t.title}"']
        levels = []
        if t.entry_price is not None:
            levels.append(f"entry {_fmt_num(t.entry_price)}")
        if t.target_price is not None:
            levels.append(f"target {_fmt_num(t.target_price)}")
        if t.invalidation_price is not None:
            levels.append(f"invalidation {_fmt_num(t.invalidation_price)}")
        if levels:
            bits.append(", ".join(levels))
        if last is not None and t.target_price is not None:
            try:
                pct = (float(last) - float(t.target_price)) / float(t.target_price) * 100.0
                bits.append(f"last {_fmt_num(last)} ({pct:+.1f}% vs target)")
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        lines.append(f"- {' — '.join(bits)}")
    return "\n".join(lines)


def _diff_block(snapshot) -> str:
    from apps.snapshots.diff import diff_sections
    from apps.snapshots.primary import previous_snapshot_for

    prev = previous_snapshot_for(snapshot)
    if prev is None:
        return ""
    delta = diff_sections(
        {s.kind: s.payload for s in prev.sections.all()},
        {s.kind: s.payload for s in snapshot.sections.all()},
    )
    if not delta or delta == "No meaningful changes.":
        return ""
    return f"### Since your last look ({prev.captured_at:%Y-%m-%d %H:%M})\n{delta}"


def _track_record_block(ticker: str) -> str:
    from apps.analytics.services.calibration import track_record_for_ticker
    from apps.thesis.models import Thesis

    top = (
        Thesis.objects.filter(ticker=ticker, status="open")
        .order_by("-conviction", "-opened_at")
        .first()
    )
    tr = track_record_for_ticker(
        ticker,
        direction=top.direction if top else None,
        conviction=top.conviction if top else None,
    )
    if tr is None:
        return ""
    c = tr["counts"]
    hr = tr["hit_rate"]
    hr_s = f" ({hr:.0%})" if hr is not None else ""
    lines = [
        "### Your track record here",
        f"- Prior closed theses on {ticker}: {tr['closed_n']} — "
        f"{c['win']} win / {c['loss']} loss{hr_s}.",
    ]
    sl = tr.get("slice")
    if sl:
        shr = f" ({sl['hit_rate']:.0%})" if sl["hit_rate"] is not None else ""
        lines.append(
            f"- Your conviction-{sl['conviction']} {sl['direction']} calls: "
            f"{sl['correct']}/{sl['n']} correct{shr}."
        )
    return "\n".join(lines)


def _recall_block(ticker: str) -> str:
    from apps.recall.services.search import related_to_ticker

    hits = related_to_ticker(ticker, k=5)
    if not hits:
        return ""
    lines = ["### You've noted this before"]
    for h in hits:
        when = h.get("source_created_at")
        when_s = when.strftime("%Y-%m-%d") if hasattr(when, "strftime") else str(when or "?")
        lines.append(
            f'- {when_s} ({h.get("kind")}): "{h.get("snippet", "")}" → {h.get("link", "")}'
        )
    return "\n".join(lines)


def assemble_coach_context(snapshot, profile) -> str:
    """The visible "what you already know" block for a snapshot-bearing run.

    Returns "" when disabled, when the snapshot has no primary_ticker, or when
    every sub-section is empty. NEVER raises — each sub-section is isolated and
    the whole thing is best-effort context, never a blocker for the run.
    """
    if profile is None or not getattr(profile, "enable_coach", False):
        return ""
    ticker = getattr(snapshot, "primary_ticker", None)
    if not ticker:
        return ""
    sections = [
        _safe(lambda: _theses_block(ticker, snapshot)),
        _safe(lambda: _diff_block(snapshot)),
        _safe(lambda: _track_record_block(ticker)),
        _safe(lambda: _recall_block(ticker)),
    ]
    body = "\n\n".join(s for s in sections if s)
    if not body:
        return ""
    header = "## 🧭 What you already know  (auto-assembled context — may be incomplete)"
    return f"{header}\n\n{body}\n\n"
