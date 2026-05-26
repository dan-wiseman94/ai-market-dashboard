"""AI payload serializer: Snapshot → single markdown string for the user message."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.token_budget import prune_to_budget


def serialize_for_ai(
    snapshot: Snapshot,
    *,
    max_tokens: int | None = None,
    provider: str = "openai",
    model: str = "",
) -> str:
    """Return the Snapshot as a compact markdown blob suitable for the `user` turn.

    The trading style belongs in the system prompt and is NOT included here.

    When `max_tokens` is None, the budget is resolved from the model catalog
    (`ModelInfo.max_payload_tokens`), defaulting to 40k when model is unknown.
    Pass `provider`/`model` so token counting uses the right tokenizer.
    """
    from apps.ai.catalog import get_model

    if max_tokens is None:
        info = get_model(provider, model) if model else None
        max_tokens = info.max_payload_tokens if info else 40_000

    sections_by_kind = {s.kind: s for s in snapshot.sections.all()}
    parts: list[str] = []

    if snapshot.objective.strip():
        parts.append(f"**Objective:** {snapshot.objective.strip()}")
    if snapshot.notes.strip():
        parts.append(f"**Notes:** {snapshot.notes.strip()}")

    ms = snapshot.market_state
    if ms and not ms.get("any_open", True):
        closed = [m for m, s in ms.get("markets", {}).items() if not s.get("is_open")]
        if closed:
            parts.append(
                f"> **Market state:** {', '.join(closed)} closed at capture — "
                f"data is as-of the last session close."
            )

    rendered: dict[str, str] = {}

    for kind in snapshot.includes:
        sec = sections_by_kind.get(kind)
        if sec is None or sec.status == "failed":
            err = sec.error if sec else "missing"
            rendered[kind] = f"## {_title(kind)}\n_(unavailable: {err})_"
            continue
        text = _render_section(kind, sec.payload)
        if text:
            rendered[kind] = text

    pruned_sections, pruned_kinds = prune_to_budget(
        rendered,
        max_tokens=max_tokens,
        provider=provider,
        model=model,
    )
    for kind in snapshot.includes:
        if kind in pruned_sections:
            parts.append(pruned_sections[kind])
    if pruned_kinds:
        parts.append(f"_(pruned for token budget: {', '.join(pruned_kinds)})_")

    return "\n\n".join(parts).strip() or "_(empty snapshot)_"


def _title(kind: str) -> str:
    return {
        "quotes": "Quotes",
        "ohlc": "OHLC",
        "chain": "Option chain",
        "positions": "Positions",
        "breadth": "Market breadth",
        "news": "News",
        "notes": "Notes",
        "image": "Chart image",
    }.get(kind, kind.title())


def _render_section(kind: str, payload) -> str:
    renderer = _RENDERERS.get(kind)
    if renderer is None:
        return f"## {_title(kind)}\n```json\n{payload}\n```"
    return renderer(payload)


def _render_quotes(payload: dict) -> str:
    if not payload:
        return "## Quotes\n_(empty)_"
    lines = [
        "## Quotes",
        "| Ticker | Last | %chg | Bid | Ask | Vol | High | Low |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
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
    lines = [
        "## Positions",
        "| Ticker | Qty | Avg | Mkt Val | Day P/L | Unrealized |",
        "|---|---:|---:|---:|---:|---:|",
    ]
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
        lines.append(
            "- Sectors: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["sectors"].items())
        )
    if payload.get("breadth"):
        lines.append(
            "- Breadth: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["breadth"].items())
        )
    return "\n".join(lines)


def _format_news_ts(it: dict) -> str:
    # `is not None` (not `or`) so epoch 0 doesn't silently fall through to published_at.
    ts_raw = it["datetime"] if it.get("datetime") is not None else it.get("published_at")
    if isinstance(ts_raw, int | float):
        return datetime.fromtimestamp(ts_raw, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    if isinstance(ts_raw, datetime):
        return ts_raw.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return str(ts_raw) if ts_raw else "?"


def _render_news(payload) -> str:
    # Trusts upstream ordering (newest-first) — see fetch_news in apps/market/services/news.py.
    items = payload.get("items", []) if isinstance(payload, dict) else (payload or [])
    if not items:
        return "## News (last 24h)\n_(no headlines)_"
    lines = ["## News (last 24h)", ""]
    for it in items[:15]:
        when = _format_news_ts(it)
        head = it.get("headline") or "?"
        src = it.get("source") or "?"
        lines.append(f"- **{when}** — *{src}* — {head}")
        summary = (it.get("summary") or "").strip()
        if summary:
            lines.append(f"  {summary}")
    return "\n".join(lines)


def _or_dash(v) -> str:
    """Render `None` as em-dash; preserve everything else (including 0/0.0/'0' — a real bid for an illiquid option)."""
    return "—" if v is None else str(v)


def _render_chain(payload: dict, *, ticker: str = "?") -> str:
    underlying = payload.get("underlying_last")
    header = f"## Option chain — {ticker}"
    if underlying:
        header += f" (underlying ${underlying})"
    expiries = payload.get("expiries") or {}
    if not expiries:
        return f"{header}\n_(no expiries)_"

    # Keep the 2 nearest expiries (sorted ascending; payload may include weeklies + monthlies).
    keep = sorted(expiries.keys())[:2]

    lines = [header]
    for exp in keep:
        section = expiries[exp]
        calls_by_strike = {c["strike"]: c for c in section.get("calls", [])}
        puts_by_strike = {p["strike"]: p for p in section.get("puts", [])}
        all_strikes = sorted(set(calls_by_strike) | set(puts_by_strike), key=lambda s: float(s))
        lines.append(f"\n### Expiry {exp}")
        lines.append(
            "| strike | call bid | call ask | call Δ | call IV | put bid | put ask | put Δ | put IV |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for strike in all_strikes:
            c = calls_by_strike.get(strike, {})
            p = puts_by_strike.get(strike, {})
            lines.append(
                f"| {strike} | {_or_dash(c.get('bid'))} | {_or_dash(c.get('ask'))} | "
                f"{_or_dash(c.get('delta'))} | {_or_dash(c.get('iv'))} | "
                f"{_or_dash(p.get('bid'))} | {_or_dash(p.get('ask'))} | "
                f"{_or_dash(p.get('delta'))} | {_or_dash(p.get('iv'))} |"
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


def build_image_blocks(image_ids: list[int], *, provider_name: str) -> list[dict]:
    """Return provider-shaped image blocks for inline base64 attachment."""
    blocks: list[dict] = []
    for img in SnapshotImage.objects.filter(id__in=image_ids).order_by("id"):
        b64 = base64.b64encode(bytes(img.data)).decode("ascii")
        if provider_name == "claude":
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img.mime_type or "image/png",
                        "data": b64,
                    },
                }
            )
        else:
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{img.mime_type or 'image/png'};base64,{b64}"},
                }
            )
    return blocks


def _render_image(payload: dict) -> str:
    ids = payload.get("image_ids") or []
    if not ids:
        return "## Charts attached\n_(none)_"
    rows = ["## Charts attached"]
    # Only metadata is rendered here; skip loading the (up to 5 MB) image BLOBs.
    images = SnapshotImage.objects.filter(id__in=ids).order_by("id").only("id", "kind", "caption")
    for img in images:
        suffix = "server-rendered" if img.kind == "server_render" else "your screenshot"
        cap = img.caption or "(no caption)"
        rows.append(f"- chart_{img.id}: {cap} ({suffix})")
    return "\n".join(rows)


_RENDERERS = {
    "quotes": _render_quotes,
    "ohlc": _render_ohlc,
    "chain": lambda p: _render_chain(p, ticker=p.get("ticker", "?")),
    "positions": _render_positions,
    "breadth": _render_breadth,
    "news": _render_news,
    "image": _render_image,
    "notes": lambda _p: "",
}
