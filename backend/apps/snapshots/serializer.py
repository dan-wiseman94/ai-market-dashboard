"""AI payload serializer: Snapshot → single markdown string for the user message."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.token_budget import prune_to_budget


def _age_str(captured_at: datetime) -> str:
    """Return a human-readable age string relative to now (UTC)."""
    now = datetime.now(UTC)
    delta = now - captured_at
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        # Captured in the future (clock skew) — just say "just now"
        return "just now"
    minutes = total_seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days >= 1:
        return f"{days} days ago" if days > 1 else "1 day ago"
    if hours >= 1:
        return f"{hours} hours ago" if hours > 1 else "1 hour ago"
    if minutes >= 1:
        return f"{minutes} minutes ago" if minutes > 1 else "1 minute ago"
    return "just now"


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
    if snapshot.manual_positions.strip():
        parts.append(
            "## Positions (manually entered — parse and reason over these)\n"
            f"{snapshot.manual_positions.strip()}"
        )

    # Capture-freshness line — always emit when captured_at is available so the AI knows
    # the data age.  Uses captured_at (auto_now_add on Snapshot, so always set after save).
    cap = snapshot.captured_at
    if cap is not None:
        ts_str = cap.strftime("%Y-%m-%d %H:%M UTC")
        age = _age_str(cap)
        parts.append(f"> **Captured:** {ts_str} ({age}).")

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
        "events": "Upcoming events",
        "overnight": "Overnight board",
        "fundamentals": "Company fundamentals",
    }.get(kind, kind.title())


def _render_section(kind: str, payload) -> str:
    renderer = _RENDERERS.get(kind)
    if renderer is None:
        return f"## {_title(kind)}\n```json\n{payload}\n```"
    return renderer(payload)


def _render_quotes(payload: dict) -> str:
    if not payload:
        return "## Quotes\n_(empty)_"
    has_gap = any(isinstance(q, dict) and q.get("gap_pct") is not None for q in payload.values())
    if has_gap:
        head = "| Ticker | Last | %chg | Gap% | PrevClose | Bid | Ask | Vol | High | Low |"
        sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    else:
        head = "| Ticker | Last | %chg | Bid | Ask | Vol | High | Low |"
        sep = "|---|---:|---:|---:|---:|---:|---:|---:|"
    lines = ["## Quotes", head, sep]
    for ticker, q in payload.items():
        row = f"| {ticker} | {_fmt(q.get('last'))} | {_fmt(q.get('pct_change'))}% |"
        if has_gap:
            row += f" {_fmt(q.get('gap_pct'))}% | {_fmt(q.get('prior_close'))} |"
        row += (
            f" {_fmt(q.get('bid'))} | {_fmt(q.get('ask'))} | {_fmt_int(q.get('volume'))} | "
            f"{_fmt(q.get('high'))} | {_fmt(q.get('low'))} |"
        )
        lines.append(row)
    return "\n".join(lines)


def _render_ohlc(payload: dict) -> str:
    bars = payload.get("bars", [])
    if not bars:
        return "## OHLC\n_(empty)_"
    header = f"## OHLC ({payload.get('ticker', '?')} @ {payload.get('timeframe', '?')})"
    if payload.get("window") == "overnight":
        header += " — overnight (extended hours)"
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
    lines = [
        "## Market breadth",
        f"- SPX: {_fmt(payload.get('spx_last'))}",
        f"- QQQ: {_fmt(payload.get('qqq_last'))}",
        f"- VIX: {_fmt(payload.get('vix_last'))}",
    ]
    if payload.get("sectors"):
        lines.append(
            "- Sectors: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["sectors"].items())
        )
    if payload.get("breadth"):
        lines.append(
            "- Breadth: " + ", ".join(f"{k}={_fmt(v)}" for k, v in payload["breadth"].items())
        )
    # Relative strength — keys in windows dict are int in Python but may be str after a
    # JSON round-trip (stored payload); .items() works for both, so no special casing needed.
    rs = payload.get("relative_strength")
    if rs and rs.get("windows"):
        bits = []
        for w, d in rs["windows"].items():
            if d.get("rs") is not None:
                bits.append(f"{w}d {d['rs']:+.2f}%")
        if bits:
            lines.append(
                f"- Relative strength ({rs['ticker']} vs {rs['benchmark']}): " + ", ".join(bits)
            )
    # Sector rotation — show leader (first) and laggard (last).
    rotation = payload.get("sector_rotation") or []
    if rotation:
        top = rotation[0]
        bot = rotation[-1]
        lines.append(
            f"- Sector rotation ({len(rotation)} sectors): "
            f"leader {top['sector']} {top['return_pct']:+.2f}%, "
            f"laggard {bot['sector']} {bot['return_pct']:+.2f}%"
        )
    return "\n".join(lines)


def _render_overnight(payload: dict) -> str:
    if not isinstance(payload, dict):
        return ""
    groups = [("Index futures", "futures"), ("Vol & rates", "vol_rates"), ("Overseas", "overseas")]
    out = ["## Overnight board"]
    any_rows = False
    for label, key in groups:
        rows = payload.get(key) or {}
        if not rows:
            continue
        any_rows = True
        out.append(f"### {label}")
        out.append("| Symbol | Last | Gap% | Prev close |")
        out.append("|---|---:|---:|---:|")
        for sym, q in rows.items():
            out.append(
                f"| {sym} | {_fmt(q.get('last'))} | {_fmt(q.get('gap_pct'))}% | "
                f"{_fmt(q.get('prior_close'))} |"
            )
    if not any_rows:
        return "## Overnight board\n_(no overnight quotes available)_"
    return "\n".join(out)


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
    overnight = isinstance(payload, dict) and payload.get("window") == "overnight"
    title = "## News (overnight, since the prior close)" if overnight else "## News (last 24h)"
    if not items:
        return f"{title}\n_(no headlines)_"
    lines = [title, ""]
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
    from apps.market.services.option_analytics import chain_analytics

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
            "| strike | call bid | call ask | call delta | call IV | put bid | put ask | put delta | put IV |"
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

    # Chain analytics — computed over ALL expiries in the payload (not just the 2 displayed).
    try:
        spot: float | None = float(underlying) if underlying else None
    except (TypeError, ValueError):
        spot = None

    flat: list[dict] = []
    for exp, section in expiries.items():
        for contract in section.get("calls", []):
            flat.append({**contract, "side": "call", "expiry": exp})
        for contract in section.get("puts", []):
            flat.append({**contract, "side": "put", "expiry": exp})

    analytics = chain_analytics(flat, spot=spot)
    lines.append("\n### Chain analytics")
    lines.append(_render_chain_analytics(analytics))

    return "\n".join(lines)


def _render_chain_analytics(a: dict) -> str:
    """Format chain_analytics() output as a compact markdown block."""
    parts: list[str] = []

    pc = a.get("put_call") or {}
    vol_r = pc.get("volume_ratio")
    oi_r = pc.get("oi_ratio")
    parts.append(
        f"- P/C volume ratio: {_fmt(vol_r) if vol_r is not None else '—'}  "
        f"| P/C OI ratio: {_fmt(oi_r) if oi_r is not None else '—'}"
    )

    mp = a.get("max_pain")
    parts.append(f"- Max-pain strike (nearest expiry): {_fmt(mp) if mp is not None else '—'}")

    skew = a.get("iv_skew_25d")
    parts.append(
        f"- 25-delta IV skew (put IV - call IV, nearest expiry): "
        f"{_fmt(skew) if skew is not None else '—'}"
    )

    ts = a.get("term_structure") or []
    if ts:
        curve = ", ".join(
            f"{t['expiry']} {_fmt(t['atm_iv']) if t['atm_iv'] is not None else '—'}" for t in ts
        )
        parts.append(f"- ATM IV term structure: {curve}")

    gex = a.get("gex") or {}
    total_gex = gex.get("total")
    flip = gex.get("flip_strike")
    gex_total_s = f"{total_gex:,.0f}" if total_gex is not None else "—"
    gex_flip_s = _fmt(flip) if flip is not None else "—"
    parts.append(f"- Dealer GEX total: {gex_total_s} | zero-gamma flip strike: {gex_flip_s}")

    return "\n".join(parts)


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


def _render_events(payload) -> str:
    earnings = payload.get("earnings", []) if isinstance(payload, dict) else []
    macro = payload.get("macro", []) if isinstance(payload, dict) else []
    if not earnings and not macro:
        return "## Upcoming events\n_(none in the next 14 days)_"
    lines = ["## Upcoming events"]
    for e in earnings:
        hint = f", {e['when_hint'].upper()}" if e.get("when_hint") else ""
        est = (e.get("detail") or {}).get("eps_est")
        est_s = f", est EPS {est}" if est is not None else ""
        lines.append(f"- {e['ticker']} earnings in {e['days_until']}d{hint}{est_s}")
    for m in macro:
        lines.append(f"- {m['title']} in {m['days_until']}d")
    return "\n".join(lines)


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


def _render_fundamentals(payload: dict) -> str:
    """Render per-ticker fundamentals as a markdown table.

    payload: {ticker: {pe, eps_ttm, rev_growth_yoy, net_margin, market_cap,
                        wk52_high, wk52_low, sector, ...}, ...}
    """
    if not payload:
        return "## Company fundamentals\n_(no fundamentals data)_"

    lines = [
        "## Company fundamentals",
        "| Ticker | P/E | EPS | Rev growth | Net margin | Mkt cap ($M) | 52wk pos | Sector |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for ticker, f in payload.items():
        if not isinstance(f, dict):
            continue
        high = f.get("wk52_high")
        low = f.get("wk52_low")
        if high is not None and low is not None and high != low:
            try:
                pos = f"{(float(high) - float(low)):.2f} range ({_fmt(low)}-{_fmt(high)})"
            except (TypeError, ValueError):
                pos = "—"
        else:
            pos = "—"
        lines.append(
            f"| {ticker} "
            f"| {_fmt(f.get('pe'))} "
            f"| {_fmt(f.get('eps_ttm'))} "
            f"| {_fmt(f.get('rev_growth_yoy'))}% "
            f"| {_fmt(f.get('net_margin'))}% "
            f"| {_fmt(f.get('market_cap'))} "
            f"| {pos} "
            f"| {f.get('sector') or '—'} |"
        )
    if len(lines) == 3:
        return "## Company fundamentals\n_(no fundamentals data)_"
    return "\n".join(lines)


_RENDERERS = {
    "quotes": _render_quotes,
    "ohlc": _render_ohlc,
    "chain": lambda p: _render_chain(p, ticker=p.get("ticker", "?")),
    "positions": _render_positions,
    "breadth": _render_breadth,
    "news": _render_news,
    "image": _render_image,
    "events": _render_events,
    "overnight": _render_overnight,
    "fundamentals": _render_fundamentals,
    "notes": lambda _p: "",
}
