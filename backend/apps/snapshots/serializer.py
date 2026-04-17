"""AI payload serializer: Snapshot → single markdown string for the user message."""
from __future__ import annotations

from apps.snapshots.models import Snapshot
from apps.snapshots.token_budget import prune_to_budget


def serialize_for_ai(snapshot: Snapshot, *, max_tokens: int = 40_000) -> str:
    """Return the Snapshot as a compact markdown blob suitable for the `user` turn.

    The trading style belongs in the system prompt and is NOT included here.
    """
    sections_by_kind = {s.kind: s for s in snapshot.sections.all()}
    parts: list[str] = []

    if snapshot.objective.strip():
        parts.append(f"**Objective:** {snapshot.objective.strip()}")
    if snapshot.notes.strip():
        parts.append(f"**Notes:** {snapshot.notes.strip()}")

    rendered: dict[str, str] = {}

    for kind in snapshot.includes:
        sec = sections_by_kind.get(kind)
        if sec is None or sec.status == "failed":
            err = (sec.error if sec else "missing")
            rendered[kind] = f"## {_title(kind)}\n_(unavailable: {err})_"
            continue
        text = _render_section(kind, sec.payload)
        if text:
            rendered[kind] = text

    pruned_sections, pruned_kinds = prune_to_budget(rendered, max_tokens=max_tokens)
    for kind in snapshot.includes:
        if kind in pruned_sections:
            parts.append(pruned_sections[kind])
    if pruned_kinds:
        parts.append(f"_(pruned for token budget: {', '.join(pruned_kinds)})_")

    return "\n\n".join(parts).strip() or "_(empty snapshot)_"


def _title(kind: str) -> str:
    return {
        "quotes": "Quotes", "ohlc": "OHLC", "chain": "Option chain",
        "positions": "Positions", "breadth": "Market breadth",
        "news": "News", "notes": "Notes", "image": "Chart image",
    }.get(kind, kind.title())


def _render_section(kind: str, payload) -> str:
    if kind == "quotes":
        return _render_quotes(payload)
    if kind == "ohlc":
        return _render_ohlc(payload)
    if kind == "chain":
        return _render_chain(payload, ticker=payload.get("ticker", "?"))
    if kind == "positions":
        return _render_positions(payload)
    if kind == "breadth":
        return _render_breadth(payload)
    if kind == "news":
        return _render_news(payload)
    if kind == "notes":
        return ""
    return f"## {_title(kind)}\n```json\n{payload}\n```"


def _render_quotes(payload: dict) -> str:
    if not payload:
        return "## Quotes\n_(empty)_"
    lines = ["## Quotes", "| Ticker | Last | %chg | Bid | Ask | Vol | High | Low |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for ticker, q in payload.items():
        lines.append(
            f"| {ticker} | {_fmt(q.get('last'))} | {_fmt(q.get('pct_change'))}% | "
            f"{_fmt(q.get('bid'))} | {_fmt(q.get('ask'))} | {_fmt_int(q.get('volume'))} | "
            f"{_fmt(q.get('high'))} | {_fmt(q.get('low'))} |"
        )
    return "\n".join(lines)


def _render_ohlc(payload: dict) -> str:
    bars = payload.get("bars", [])
    if not bars:
        return "## OHLC\n_(empty)_"
    header = f"## OHLC ({payload.get('ticker', '?')} @ {payload.get('timeframe', '?')})"
    csv_lines = ["ts,open,high,low,close,volume"]
    for b in bars:
        csv_lines.append(f"{b['ts']},{b['open']},{b['high']},{b['low']},{b['close']},{b['volume']}")
    return f"{header}\n```csv\n" + "\n".join(csv_lines) + "\n```"


def _render_positions(payload: list) -> str:
    if not payload:
        return "## Positions\n_(empty)_"
    lines = ["## Positions", "| Ticker | Qty | Avg | Mkt Val | Day P/L | Unrealized |",
             "|---|---:|---:|---:|---:|---:|"]
    total_day = total_unrl = 0.0
    for p in payload:
        total_day += p.get("day_pl") or 0
        total_unrl += p.get("unrealized_pl") or 0
        lines.append(
            f"| {p['ticker']} | {_fmt(p.get('qty'))} | {_fmt(p.get('avg_cost'))} | "
            f"{_fmt(p.get('mkt_value'))} | {_fmt(p.get('day_pl'))} | {_fmt(p.get('unrealized_pl'))} |"
        )
    lines.append(f"| **Total** |  |  |  | **{total_day:.2f}** | **{total_unrl:.2f}** |")
    return "\n".join(lines)


def _render_breadth(payload: dict) -> str:
    lines = ["## Market breadth"]
    lines.append(f"- SPY: {_fmt(payload.get('spy_last'))}")
    lines.append(f"- QQQ: {_fmt(payload.get('qqq_last'))}")
    lines.append(f"- VIX: {_fmt(payload.get('vix_last'))}")
    if payload.get("sectors"):
        lines.append("- Sectors: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["sectors"].items()))
    if payload.get("breadth"):
        lines.append("- Breadth: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["breadth"].items()))
    return "\n".join(lines)


def _render_news(payload: list) -> str:
    if not payload:
        return "## News\n_(no headlines)_"
    lines = ["## News"]
    for item in payload[:15]:
        lines.append(f"- **{item.get('headline', '?')}** — {item.get('summary', '')} ({item.get('source', '')})")
    return "\n".join(lines)


def _render_chain(payload: dict, *, ticker: str = "?") -> str:
    underlying = payload.get("underlying_last")
    header = f"## Option chain — {ticker} (underlying ${underlying})" if underlying else f"## Option chain — {ticker}"
    expiries = payload.get("expiries") or {}
    if not expiries:
        return f"{header}\n_(no expiries)_"

    # Front-month + next monthly per spec §5.3 — keep first 2 expiries by sorted date.
    keep = list(sorted(expiries.keys()))[:2]

    lines = [header]
    for exp in keep:
        section = expiries[exp]
        calls_by_strike = {c["strike"]: c for c in section.get("calls", [])}
        puts_by_strike = {p["strike"]: p for p in section.get("puts", [])}
        all_strikes = sorted(set(calls_by_strike) | set(puts_by_strike), key=lambda s: float(s))
        lines.append(f"\n### Expiry {exp}")
        lines.append("| strike | call bid | call ask | call Δ | call IV | put bid | put ask | put Δ | put IV |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for strike in all_strikes:
            c = calls_by_strike.get(strike, {})
            p = puts_by_strike.get(strike, {})
            lines.append(
                f"| {strike} | {c.get('bid') or '—'} | {c.get('ask') or '—'} | "
                f"{c.get('delta') or '—'} | {c.get('iv') or '—'} | "
                f"{p.get('bid') or '—'} | {p.get('ask') or '—'} | "
                f"{p.get('delta') or '—'} | {p.get('iv') or '—'} |"
            )
    return "\n".join(lines)


def _fmt(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.2f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_int(v) -> str:
    if v is None:
        return "—"
    try:
        return f"{int(v):,}"
    except (TypeError, ValueError):
        return str(v)
