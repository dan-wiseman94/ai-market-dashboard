"""Serialize news items into Anthropic `search_result` blocks with citations on.

Using search_result blocks lets Claude emit citations that point back at each
item so the UI can render hoverable superscripts. The UI resolves a citation
by matching its `source` field against `news://<id>` or the original url.
"""
from __future__ import annotations


def news_to_search_result_blocks(items: list[dict]) -> list[dict]:
    blocks: list[dict] = []
    for it in items:
        url = it.get("url") or ""
        source = url or f"news://{it.get('id')}"
        title = (it.get("headline") or "")[:200]
        body_parts: list[str] = []
        src = it.get("source") or ""
        if src:
            body_parts.append(f"Source: {src}")
        summary = (it.get("summary") or "").strip()
        if summary:
            body_parts.append(summary)
        text = "\n".join(body_parts) or title
        blocks.append({
            "type": "search_result",
            "source": source,
            "title": title,
            "content": [{"type": "text", "text": text}],
            "citations": {"enabled": True},
        })
    return blocks
