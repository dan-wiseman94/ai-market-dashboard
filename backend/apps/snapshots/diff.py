"""Pairwise snapshot diff for AI context.

Compares two already-serialized `sections` dicts (as stored on Snapshot) and
emits a compact markdown delta. The goal is *signal compression*: feed the
AI a paragraph that says what changed, not two 50k-token payloads.
"""

from __future__ import annotations

from typing import Any

_NOISE_PCT = 0.005  # 0.5% — movements below this don't go into the diff


def diff_sections(prev: dict[str, Any], curr: dict[str, Any]) -> str:
    """Return a markdown delta between two section dicts.

    Both inputs are {"kind": <section payload>} — shape matches what the
    snapshot services store. Missing keys on either side are handled.
    """
    lines: list[str] = []
    all_kinds = set(prev) | set(curr)

    for kind in sorted(all_kinds):
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

    return "\n".join(lines) if lines else "No meaningful changes."


def _as_dict(payload: Any) -> dict:
    """Coerce an unexpected payload shape to {} so the diff never raises."""
    return payload if isinstance(payload, dict) else {}


def _news_items(payload: Any) -> list:
    """News is stored as {"items": [...]}; tolerate a bare list for back-compat."""
    if isinstance(payload, dict):
        return payload.get("items") or []
    return payload or []


def _headline(item: dict) -> str:
    return item.get("headline") or item.get("title") or "(untitled)"


def _summarize_new(kind: str, payload: Any) -> str:
    if kind == "quotes" and isinstance(payload, dict):
        return ", ".join(f"{t}={q.get('last', '?')}" for t, q in list(payload.items())[:8])
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
