"""AI payload serializer: Snapshot → single markdown string for the user message."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from apps.snapshots.image_store import read_image_bytes
from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.token_budget import estimate_tokens, prune_to_budget

# Never truncate the OHLC tail below this many bars — fewer stops being a price
# path; at that point dropping the section (prune_to_budget) is more honest.
_OHLC_MIN_BARS = 30


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
            "## Positions (current holdings — manually entered; parse and reason over these)\n"
            f"{snapshot.manual_positions.strip()}"
        )
    if snapshot.candidate_positions.strip():
        parts.append(
            "## Candidate positions (potential trades under consideration — "
            "evaluate the entry case, do not assume these are held)\n"
            f"{snapshot.candidate_positions.strip()}"
        )

    # Capture-freshness line — always emit when captured_at is available so the AI knows
    # the data age.  Uses captured_at (auto_now_add on Snapshot, so always set after save).
    cap = snapshot.captured_at
    if cap is not None:
        ts_str = cap.strftime("%Y-%m-%d %H:%M UTC")
        age = _age_str(cap)
        parts.append(f"> **Captured:** {ts_str} ({age}).")

    parts.extend(_market_state_lines(snapshot.market_state))

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

    ohlc_sec = sections_by_kind.get("ohlc")
    if "ohlc" in rendered and ohlc_sec is not None:
        rendered = _shrink_ohlc_to_budget(
            rendered,
            ohlc_payload=ohlc_sec.payload or {},
            max_tokens=max_tokens,
            provider=provider,
            model=model,
        )

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


def _market_state_lines(ms: dict | None) -> list[str]:
    """Blockquote caveats about market phase at capture time."""
    lines: list[str] = []
    if ms and not ms.get("any_open", True):
        closed = [m for m, s in ms.get("markets", {}).items() if not s.get("is_open")]
        if closed:
            lines.append(
                f"> **Market state:** {', '.join(closed)} closed at capture — "
                f"data is as-of the last session close."
            )
    # A futures-open capture keeps any_open True while equities sit premarket —
    # flag it, or zeroed day fields and warm-up breadth read as real numbers.
    eq_phase = ((ms or {}).get("markets", {}).get("us_equity") or {}).get("phase")
    if eq_phase in ("premarket", "postmarket"):
        lines.append(
            f"> **Market state:** US equities in {eq_phase} at capture — day-session "
            f"fields (day high/low, breadth internals) may be incomplete."
        )
    return lines


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
        "vix": "VIX term structure",
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


def _ohlc_gap_note(bars: list[dict]) -> str:
    """Return a one-line caveat if bars contain a material history gap, else ''.

    Algorithm:
    - Parse the 'ts' field of each bar as an ISO datetime and compute consecutive deltas.
    - Sort the deltas and take the median of the lower half as the 'typical' interval
      (robust to a single large gap polluting the overall median).
    - Flag the largest delta when it is >= 4x the typical interval (conservative: handles
      Fri->Mon 3-calendar-day weekends without false-positives; only fires on clear multi-
      session holes like 7+ calendar days for daily bars).
    - Returns '' when data is contiguous or when bars are too few to assess (<= 2 bars).
    """
    if len(bars) < 3:
        return ""

    timestamps: list[datetime] = []
    for b in bars:
        raw = b.get("ts")
        if raw is None:
            return ""
        try:
            dt = datetime.fromisoformat(str(raw))
            # Ensure timezone-aware for consistent subtraction
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            timestamps.append(dt)
        except (ValueError, TypeError):
            return ""

    if len(timestamps) < 3:
        return ""

    deltas_s = sorted(
        [(timestamps[i + 1] - timestamps[i]).total_seconds() for i in range(len(timestamps) - 1)]
    )

    lower_half = deltas_s[: max(1, len(deltas_s) // 2)]
    typical_s = lower_half[len(lower_half) // 2]

    if typical_s <= 0:
        return ""

    max_s = deltas_s[-1]  # already sorted ascending

    if max_s < 4 * typical_s:
        return ""

    # Find which consecutive pair produced the largest delta (unsorted timestamps needed)
    raw_deltas = [
        (timestamps[i + 1] - timestamps[i]).total_seconds() for i in range(len(timestamps) - 1)
    ]
    gap_idx = max(range(len(raw_deltas)), key=lambda i: raw_deltas[i])
    before = timestamps[gap_idx].strftime("%Y-%m-%d")
    after = timestamps[gap_idx + 1].strftime("%Y-%m-%d")

    return f"_(history gap: largest hole between {before} and {after})_"


def _ohlc_csv(bars: list[dict], ticker: str) -> str:
    """Bars as a fenced CSV block. Cash indices ($SPX, $TNX, ...) don't trade —
    providers truthfully report volume 0 on every bar — so an all-zero/absent
    volume series drops the column (with a note) rather than shipping rows of
    zeros the AI reads as a broken feed."""
    has_volume = any(b.get("volume") for b in bars)
    if has_volume:
        csv_lines = ["ts,open,high,low,close,volume"]
        for b in bars:
            csv_lines.append(
                f"{b['ts']},{b['open']},{b['high']},{b['low']},{b['close']},{b.get('volume')}"
            )
    else:
        csv_lines = ["ts,open,high,low,close"]
        for b in bars:
            csv_lines.append(f"{b['ts']},{b['open']},{b['high']},{b['low']},{b['close']}")
    result = "```csv\n" + "\n".join(csv_lines) + "\n```"
    if not has_volume:
        result += (
            f"\n_({ticker} reports no traded volume (cash indices don't trade) — volume "
            "column omitted; use a liquid proxy ETF for volume confirmation)_"
        )
    return result


def _render_ohlc(payload: dict) -> str:
    bars = payload.get("bars", [])
    if not bars:
        return "## OHLC\n_(empty)_"
    ticker = payload.get("ticker", "?")
    header = f"## OHLC ({ticker} @ {payload.get('timeframe', '?')})"
    if payload.get("window") == "24h":
        header += (
            " — last 24h (1m recent, 5m earlier)"
            if payload.get("coarse_timeframe")
            else " — last 24h"
        )
    result = f"{header}\n" + _ohlc_csv(bars, ticker)
    truncated_from = payload.get("truncated_from")
    if truncated_from:
        result += (
            f"\n_(showing newest {len(bars)} of {truncated_from} bars — "
            "older bars trimmed to fit the token budget)_"
        )
    gap_note = _ohlc_gap_note(bars)
    if gap_note:
        result += f"\n{gap_note}"
    for wl_ticker, wl_bars in (payload.get("watchlist_daily") or {}).items():
        if wl_bars:
            result += f"\n\n### {wl_ticker} — daily ({len(wl_bars)} bars)\n" + _ohlc_csv(
                wl_bars, wl_ticker
            )
    if payload.get("watchlist_daily_omitted"):
        result += "\n\n_(per-ticker watchlist daily history omitted to fit the token budget)_"
    return result


def _shrink_ohlc_to_budget(
    rendered: dict[str, str],
    *,
    ohlc_payload: dict,
    max_tokens: int,
    provider: str,
    model: str,
) -> dict[str, str]:
    """Truncate the OHLC bars (oldest first) when the total overflows the budget.

    Without this, ``prune_to_budget`` can only drop whole sections — a bloated
    bar dump would cost the entire price history (and, before OHLC in the old
    prune order, the news). Keeping the newest tail preserves the recent price
    path the AI actually reasons over.
    """
    bars = ohlc_payload.get("bars") or []
    sizes = {k: estimate_tokens(v, provider=provider, model=model) for k, v in rendered.items()}
    total = sum(sizes.values())
    if total <= max_tokens:
        return rendered

    # Over budget: sacrifice the watchlist-daily enrichment before the primary
    # series loses a single bar — the intraday path is what the AI reasons over.
    if ohlc_payload.get("watchlist_daily"):
        ohlc_payload = {**ohlc_payload, "watchlist_daily": {}, "watchlist_daily_omitted": True}
        rendered = {**rendered, "ohlc": _render_ohlc(ohlc_payload)}
        sizes["ohlc"] = estimate_tokens(rendered["ohlc"], provider=provider, model=model)
        total = sum(sizes.values())
        if total <= max_tokens:
            return rendered

    if len(bars) <= _OHLC_MIN_BARS:
        return rendered

    headroom = max_tokens - (total - sizes["ohlc"])
    if headroom <= 0:
        return rendered  # other sections alone overflow — leave it to the pruner

    keep = max(_OHLC_MIN_BARS, int(len(bars) * headroom / sizes["ohlc"] * 0.9))
    while True:
        keep = min(keep, len(bars))
        shrunk = {**ohlc_payload, "bars": bars[-keep:], "truncated_from": len(bars)}
        text = _render_ohlc(shrunk)
        fits = estimate_tokens(text, provider=provider, model=model) <= headroom
        if fits or keep <= _OHLC_MIN_BARS:
            return {**rendered, "ohlc": text}
        keep = max(_OHLC_MIN_BARS, keep // 2)


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
    title = "## News (last 24h)"
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

    # Options-implied expected move (1σ): frame the AI's call against what's priced.
    # Reuse the term structure already in `analytics` instead of re-flattening the
    # chain and re-running chain_analytics inside term_structure(payload).
    from apps.market.services.expected_move import moves_from_term_structure

    em_rows = moves_from_term_structure(analytics.get("term_structure") or [], spot)
    if em_rows:
        priced = " · ".join(f"±{r['move_pct'] * 100:.1f}% ({r['horizon_days']}d)" for r in em_rows)
        lines.append(f"\n**Options-implied move (1σ):** {priced}")

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
        b64 = base64.b64encode(read_image_bytes(img)).decode("ascii")
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


_LIVE_YIELD_TENOR_ORDER = ("13W", "2Y", "5Y", "10Y", "30Y")


def _render_macro(payload: dict) -> str:
    """FRED series table with as-of dates plus best-effort live Treasury yields.

    The lag note is load-bearing: FRED daily series (DGS*) publish ~1 business
    day behind (weekends widen it), and without the note the AI reads the as-of
    dates as a stale/broken feed instead of normal source lag.
    """
    if not isinstance(payload, dict):
        return "## Macro\n_(empty)_"
    series = payload.get("series")
    live = payload.get("live_yields") or {}
    if not isinstance(series, dict):
        # Legacy flat payloads: {series_id: {label, value, prev, change, date}}.
        series = {k: v for k, v in payload.items() if isinstance(v, dict) and "label" in v}
        live = {}
    if not series and not live:
        return "## Macro\n_(empty)_"
    lines = ["## Macro"]
    if series:
        lines += ["| Series | Value | Prev | Δ | As of |", "|---|---:|---:|---:|---|"]
        for s in series.values():
            lines.append(
                f"| {s.get('label')} | {_fmt(s.get('value'))} | {_fmt(s.get('prev'))} | "
                f"{_fmt(s.get('change'))} | {s.get('date') or '—'} |"
            )
        lines.append(
            "_(FRED daily series publish with a ~1-business-day lag (weekends widen it) — "
            "'As of' shows the latest observation the source has released, not a stale feed)_"
        )
    if live:
        lines += ["", "**Live Treasury yields** (CBOE yield indices at capture time):"]
        lines += ["| Tenor | Yield % |", "|---|---:|"]
        for tenor in _LIVE_YIELD_TENOR_ORDER:
            y = live.get(tenor)
            if y:
                lines.append(f"| {tenor} | {_fmt(y.get('yield_pct'))} |")
    return "\n".join(lines)


def _signed_pct(v) -> str:
    return f" ({v:+.2f}%)" if isinstance(v, int | float) else ""


def _render_vix(payload) -> str:
    """Spot $VIX vs /VX futures legs. Always-on section: a degenerate payload
    renders an explicit empty marker rather than vanishing from the prompt."""
    if not isinstance(payload, dict) or not payload:
        return "## VIX term structure\n_(empty)_"
    lines = ["## VIX term structure"]
    spot = payload.get("spot")
    if isinstance(spot, dict):
        lines.append(
            f"- Spot {spot.get('symbol', '$VIX')}: "
            f"{_fmt(spot.get('last'))}{_signed_pct(spot.get('pct_change'))}"
        )
    front = payload.get("front")
    if isinstance(front, dict):
        label = "(continuous)" if front.get("continuous") else f"(exp {front.get('expiry')})"
        line = (
            f"- Front {front.get('symbol')} {label}: "
            f"{_fmt(front.get('last'))}{_signed_pct(front.get('pct_change'))}"
        )
        basis = front.get("basis")
        if isinstance(basis, int | float):
            line += f", basis {basis:+.2f}"
            basis_pct = front.get("basis_pct")
            if isinstance(basis_pct, int | float):
                line += f" ({basis_pct:+.2f}% vs spot)"
        lines.append(line)
    second = payload.get("second")
    if isinstance(second, dict):
        lines.append(
            f"- Second {second.get('symbol')} (exp {second.get('expiry')}): "
            f"{_fmt(second.get('last'))}{_signed_pct(second.get('pct_change'))}"
        )
    contango = payload.get("contango_pct")
    if isinstance(contango, int | float) and payload.get("structure"):
        lines.append(f"- Structure: {payload['structure']} ({contango:+.2f}% front→second)")
    note = payload.get("note")
    if note:
        lines.append(f"_({note})_")
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
    "macro": _render_macro,
    "notes": lambda _p: "",
    "vix": _render_vix,
}
