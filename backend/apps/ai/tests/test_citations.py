"""Citations module emits Anthropic search_result blocks for news items."""
from __future__ import annotations

from apps.ai.citations import news_to_search_result_blocks


def test_single_news_item_becomes_search_result_block() -> None:
    items = [{
        "id": 42, "headline": "FOMC holds", "summary": "No change.",
        "source": "Bloomberg", "url": "https://example.com/a", "datetime": 1_700_000_000,
    }]
    blocks = news_to_search_result_blocks(items)
    assert len(blocks) == 1
    b = blocks[0]
    assert b["type"] == "search_result"
    assert b["source"] == "https://example.com/a"
    assert b["title"] == "FOMC holds"
    assert b["citations"] == {"enabled": True}
    assert isinstance(b["content"], list) and b["content"][0]["type"] == "text"
    assert "No change." in b["content"][0]["text"]


def test_many_items_each_become_one_block() -> None:
    items = [{
        "id": i, "headline": f"H{i}", "summary": "",
        "source": "", "url": f"https://x/{i}", "datetime": 0,
    } for i in range(3)]
    blocks = news_to_search_result_blocks(items)
    assert len(blocks) == 3
    sources = [b["source"] for b in blocks]
    assert sources == ["https://x/0", "https://x/1", "https://x/2"]


def test_missing_url_falls_back_to_id_pseudo_uri() -> None:
    items = [{
        "id": 7, "headline": "H", "summary": "S",
        "source": "", "url": "", "datetime": 0,
    }]
    blocks = news_to_search_result_blocks(items)
    assert blocks[0]["source"] == "news://7"


def test_empty_items_returns_empty_list() -> None:
    assert news_to_search_result_blocks([]) == []
