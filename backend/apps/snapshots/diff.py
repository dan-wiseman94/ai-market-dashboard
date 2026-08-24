"""Pairwise snapshot diff for AI context.

Compares two already-serialized `sections` dicts (as stored on Snapshot) and
emits a compact markdown delta. The goal is *signal compression*: feed the
AI a paragraph that says what changed, not two 50k-token payloads.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

_NOISE_PCT = 0.005  # 0.5% — movements below this don't go into the diff


def diff_sections(prev: dict[str, Any], curr: dict[str, Any]) -> str:
    """Return a markdown delta between two section dicts.

    Both inputs are {"kind": <section payload>} — shape matches what the
    snapshot services store. Missing keys on either side are handled.
    """
    lines: list[str] = []
    all_kinds = set(prev) | set(curr)

    for kind in sorted(all_kinds):
        # Per-section isolation: a single malformed section payload must never
        # take down the whole diff (the endpoint would 400 via core.exception_handler).
        # Skip the offending section and keep the rest — the diff "never raises" intent.
        try:
            p = prev.get(kind)
            c = curr.get(kind)
            if p is None and c is not None:
                lines.append(f"**{kind}**: new this capture")
                summary = _summarize_new(kind, c)
                if summary:
                    lines.append(summary)
            elif c is None and p is not None:
                lines.append(f"**{kind}**: removed/dropped from this capture")
            else:
                delta = _diff_one(kind, p, c)
                if delta:
                    lines.append(f"**{kind}**:")
                    lines.append(delta)
        except Exception:
            log.warning("diff_section_skipped kind=%s", kind, exc_info=True)
            continue

    return "\n".join(lines) if lines else "No meaningful changes."


def _as_dict(payload: Any) -> dict:
    """Coerce an unexpected payload shape to {} so the diff never raises."""
    return payload if isinstance(payload, dict) else {}


def _news_items(payload: Any) -> list:
    """News is stored as {"items": [...]}; tolerate a bare list."""
    if isinstance(payload, dict):
        return payload.get("items") or []
    return payload or []


def _headline(item: dict) -> str:
    return item.get("headline") or item.get("title") or "(untitled)"


def _summarize_new(kind: str, payload: Any) -> str:
    if kind == "quotes" and isinstance(payload, dict):
        return ", ".join(
            f"{t}={q.get('last', '?')}" for t, q in list(payload.items())[:8] if isinstance(q, dict)
        )
    if kind == "news":
        return "\n".join(f"- {_headline(item)}" for item in _news_items(payload)[:5])
    return "(section content added)"


def _diff_one(kind: str, prev: Any, curr: Any) -> str:
    if kind == "quotes":
        return _diff_quotes(_as_dict(prev), _as_dict(curr))
    if kind == "news":
        return _diff_news(_news_items(prev), _news_items(curr))
    if kind == "breadth":
        return _diff_breadth(_as_dict(prev), _as_dict(curr))
    if kind == "positions":
        return _diff_positions(prev, curr)
    if kind == "ohlc":
        return _diff_ohlc(_as_dict(prev), _as_dict(curr))
    if kind == "chain":
        return _diff_chain(_as_dict(prev), _as_dict(curr))
    if kind == "overnight":
        return _diff_overnight(_as_dict(prev), _as_dict(curr))
    if kind == "vix":
        return _diff_vix(_as_dict(prev), _as_dict(curr))
    return ""


def _diff_quotes(prev: dict, curr: dict) -> str:
    rows: list[str] = []
    for ticker, c in curr.items():
        # Quote values are normally {last, ...}; tolerate anything else without
        # raising — this endpoint must never 500 on an unexpected payload shape.
        if not isinstance(c, dict):
            continue
        p = _as_dict(prev.get(ticker))
        p_last = p.get("last")
        c_last = c.get("last")
        if p_last is None or c_last is None:
            continue
        try:
            change = (c_last - p_last) / p_last if p_last else 0.0
        except (TypeError, ZeroDivisionError):
            continue
        if abs(change) < _NOISE_PCT:
            continue
        sign = "+" if change >= 0 else ""
        rows.append(f"- {ticker}: {p_last:g} → {c_last:g} ({sign}{change * 100:.2f}%)")
    return "\n".join(rows) if rows else "- (all watchlist moves below 0.5%)"


def _diff_news(prev: list, curr: list) -> str:
    prev_ids = {item.get("id") for item in prev if isinstance(item, dict)}
    new_items = [item for item in curr if isinstance(item, dict) and item.get("id") not in prev_ids]
    if not new_items:
        return "- (no new headlines)"
    return "\n".join(f"- {_headline(item)}" for item in new_items[:10])


def _diff_breadth(prev: dict, curr: dict) -> str:
    rows: list[str] = []
    for key in ("spx_last", "qqq_last", "vix_last"):
        p_val = prev.get(key)
        c_val = curr.get(key)
        if p_val is not None and c_val is not None and p_val != c_val:
            rows.append(f"- {key}: {p_val} → {c_val}")
    return "\n".join(rows) if rows else ""


def _diff_positions(prev: Any, curr: Any) -> str:
    def by_sym(rows: Any) -> dict:
        return (
            {r.get("symbol"): r for r in rows if isinstance(r, dict)}
            if isinstance(rows, list)
            else {}
        )

    p, c = by_sym(prev), by_sym(curr)
    rows = []
    for sym, cur in c.items():
        pr = p.get(sym)
        if pr is None:
            rows.append(f"- {sym}: opened (P/L {cur.get('unrealized_pl', '?')})")
        elif pr.get("unrealized_pl") != cur.get("unrealized_pl"):
            rows.append(f"- {sym}: P/L {pr.get('unrealized_pl')} → {cur.get('unrealized_pl')}")
    for sym in p.keys() - c.keys():
        rows.append(f"- {sym}: closed")
    return "\n".join(rows)


def _diff_ohlc(prev: dict, curr: dict) -> str:
    def last_close(blob: dict) -> Any:
        inner = blob.get("data", blob)
        if not isinstance(inner, dict):
            return None
        bars = inner.get("bars")
        if isinstance(bars, list) and bars and isinstance(bars[-1], dict):
            return bars[-1].get("close")
        return None

    pc, cc = last_close(prev), last_close(curr)
    inner = curr.get("data", curr)
    t = inner.get("ticker", "") if isinstance(inner, dict) else ""
    if pc is not None and cc is not None and pc != cc:
        return f"- {t} last: {pc} → {cc}"
    return ""


def _diff_overnight(prev: dict, curr: dict) -> str:
    rows: list[str] = []
    for group in ("futures", "vol_rates", "overseas"):
        p = _as_dict(prev.get(group))
        c = _as_dict(curr.get(group))
        for sym, cq in c.items():
            if not isinstance(cq, dict):
                continue
            pq = _as_dict(p.get(sym))
            p_last, c_last = pq.get("last"), cq.get("last")
            if p_last is None or c_last is None:
                continue
            try:
                change = (c_last - p_last) / p_last if p_last else 0.0
            except (TypeError, ZeroDivisionError):
                continue
            if abs(change) < _NOISE_PCT:
                continue
            sign = "+" if change >= 0 else ""
            rows.append(f"- {sym}: {p_last:g} → {c_last:g} ({sign}{change * 100:.2f}%)")
    return "\n".join(rows) if rows else "- (overnight board moves below 0.5%)"


def _diff_vix(prev: dict, curr: dict) -> str:
    """A structure flip is the headline vol signal; contango uses an absolute
    0.5-point gate (it is already a percentage), spot/front the relative one."""
    rows: list[str] = []
    p_struct, c_struct = prev.get("structure"), curr.get("structure")
    if p_struct and c_struct and p_struct != c_struct:
        rows.append(f"- structure: {p_struct} → {c_struct}")
    p_ct, c_ct = prev.get("contango_pct"), curr.get("contango_pct")
    if isinstance(p_ct, int | float) and isinstance(c_ct, int | float) and abs(c_ct - p_ct) >= 0.5:
        rows.append(f"- contango: {p_ct:+.2f}% → {c_ct:+.2f}%")
    for leg in ("spot", "front"):
        c_leg = _as_dict(curr.get(leg))
        p_last, c_last = _as_dict(prev.get(leg)).get("last"), c_leg.get("last")
        if p_last is None or c_last is None:
            continue
        try:
            change = (c_last - p_last) / p_last if p_last else 0.0
        except (TypeError, ZeroDivisionError):
            continue
        if abs(change) < _NOISE_PCT:
            continue
        sign = "+" if change >= 0 else ""
        rows.append(
            f"- {leg} ({c_leg.get('symbol')}): {p_last:g} → {c_last:g} ({sign}{change * 100:.2f}%)"
        )
    return "\n".join(rows)


def _diff_chain(prev: dict, curr: dict) -> str:
    # Compact: report change in the count of expiries; deep greek diffs deferred.
    # The chain payload stores expiries as a DICT keyed by expiry date
    # ({"expiries": {date: section}}) — reading a non-existent "expirations"
    # list would silently never report chain changes.
    def n(blob: dict) -> int | None:
        exp = blob.get("expiries")
        if exp is None:
            data = blob.get("data")
            exp = data.get("expiries") if isinstance(data, dict) else None
        return len(exp) if isinstance(exp, dict | list) else None

    pn, cn = n(prev), n(curr)
    if pn is not None and cn is not None and pn != cn:
        return f"- expiries: {pn} → {cn}"
    return ""
