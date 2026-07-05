from apps.snapshots.serializer import _render_news

PAYLOAD = {
    "items": [
        {
            "headline": "Fed minutes show split",
            "source": "Reuters",
            "summary": "Hawks vs doves",
            "url": "https://x/1",
            "datetime": 1745484720,
            "related": "SPY",
        },
        {
            "headline": "TSLA Q1 deliveries miss",
            "source": "Bloomberg",
            "summary": "",
            "url": "https://x/2",
            "datetime": 1745482800,
            "related": "TSLA",
        },
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
    big = {
        "items": [
            {
                "headline": f"H{i}",
                "source": "S",
                "summary": "",
                "url": "u",
                "datetime": 1745484720 - i,
                "related": "",
            }
            for i in range(30)
        ]
    }
    md = _render_news(big)
    assert md.count("- **") == 15


def test_render_news_handles_empty():
    assert "_(no headlines)_" in _render_news({"items": []})


def test_render_news_accepts_bare_list():
    items = [
        {
            "headline": "Bare list headline",
            "source": "L",
            "summary": "",
            "datetime": 1745484720,
            "related": "X",
        },
    ]
    md = _render_news(items)
    assert "Bare list headline" in md
    assert "*L*" in md


def test_render_news_handles_datetime_object_in_published_at():
    """ORM-hydrated NewsItem rows put a datetime object in `published_at`; format must match the int path."""
    from datetime import UTC
    from datetime import datetime as dt

    items = [
        {
            "headline": "From ORM",
            "source": "S",
            "summary": "",
            "published_at": dt(2026, 4, 17, 9, 12, tzinfo=UTC),
        },
    ]
    md = _render_news(items)
    assert "2026-04-17 09:12 UTC" in md
    assert "From ORM" in md


def test_render_news_does_not_fall_through_on_epoch_zero_datetime():
    """`datetime=0` is a valid (if unusual) value — must not be replaced by published_at fallback."""
    items = [
        {
            "headline": "Epoch",
            "source": "S",
            "summary": "",
            "datetime": 0,
            "published_at": "WRONG-FALLBACK",
        },
    ]
    md = _render_news(items)
    assert "1970-01-01 00:00 UTC" in md
    assert "WRONG-FALLBACK" not in md
