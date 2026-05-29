from __future__ import annotations

import hashlib


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _message_text(msg) -> str:
    c = msg.content or {}
    if isinstance(c, dict):
        if "text" in c:
            return str(c["text"])
        if "blocks" in c:
            return "\n".join(b.get("text", "") for b in c["blocks"] if isinstance(b, dict))
    return str(c)


def build_text(kind: str, obj) -> str:
    if kind == "message":
        return _message_text(obj)[:8000]
    if kind == "snapshot":
        from apps.snapshots.serializer import serialize_for_ai

        return serialize_for_ai(obj, max_tokens=2000)
    if kind == "thesis":
        return f"{obj.title}\n{obj.rationale}\n{obj.ticker} {obj.direction}"
    if kind == "journal":
        return obj.note or ""
    if kind == "postmortem":
        r = obj.report or {}
        return (
            " ".join(str(r.get(k, "")) for k in ("summary", "lessons", "what_missed"))
            or obj.verdict
        )
    if kind == "observation":
        return _message_text(obj)[:8000]
    return ""


def extract_tickers(kind: str, obj) -> list[str]:
    if kind == "thesis":
        return [obj.ticker.upper()] if obj.ticker else []
    snap = (
        getattr(obj, "snapshot_ref", None)
        or getattr(obj, "snapshot", None)
        or (obj if kind == "snapshot" else None)
    )
    pt = getattr(snap, "primary_ticker", None)
    return [pt] if pt else []
