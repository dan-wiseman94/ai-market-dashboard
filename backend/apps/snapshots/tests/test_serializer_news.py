from apps.snapshots.serializer import _render_news

PAYLOAD = {
    "items": [
        {"headline": "Fed minutes show split", "source": "Reuters", "summary": "Hawks vs doves",
         "url": "https://x/1", "datetime": 1745484720, "related": "SPY"},
        {"headline": "TSLA Q1 deliveries miss", "source": "Bloomberg", "summary": "",
         "url": "https://x/2", "datetime": 1745482800, "related": "TSLA"},
    ],
}


def test_render_news_emits_dated_list():
    md = _render_news(PAYLOAD)
    assert "## News (last 24h)" in md
    assert "Fed minutes show split" in md
    assert "*Reuters*" in md
    assert "Hawks vs doves" in md
    assert "TSLA Q1 deliveries miss" in md
    assert "*Bloomberg*" in md


def test_render_news_caps_at_15():
    big = {"items": [
        {"headline": f"H{i}", "source": "S", "summary": "", "url": "u",
         "datetime": 1745484720 - i, "related": ""} for i in range(30)
    ]}
    md = _render_news(big)
    assert md.count("- **") == 15


def test_render_news_handles_empty():
    assert "_(no headlines)_" in _render_news({"items": []})
