"""Tests for the Federal Reserve RSS service (fed.py).

No Django DB required — the service has no model upserts. All external I/O
and the Redis cache are patched; no real network calls or Redis connections
are made (mirrors test_treasury.py / test_edgar.py).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests as _req

from apps.market.services import fed as fed_mod

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Federal Reserve issues FOMC statement</title>
<link>https://www.federalreserve.gov/x.htm</link>
<pubDate>Wed, 16 Sep 2026 18:00:00 GMT</pubDate>
<description>Statement text.</description></item>
</channel></rss>"""

_PASSTHROUGH_CACHE = lambda key, *, ttl_seconds, fetcher: fetcher()  # noqa: E731


def test_parse_extracts_items():
    items = fed_mod._parse("press_monetary", RSS)
    assert items[0]["title"].startswith("Federal Reserve issues")
    assert items[0]["published"].startswith("2026-09-16")
    assert items[0]["kind"] == "press_monetary"
    assert items[0]["url"] == "https://www.federalreserve.gov/x.htm"
    assert items[0]["summary"] == "Statement text."


def test_parse_skips_items_without_title():
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
    <item><link>https://www.federalreserve.gov/x.htm</link></item>
    </channel></rss>"""
    assert fed_mod._parse("speeches", rss) == []


def test_parse_handles_missing_or_unparseable_pubdate():
    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
    <item><title>No date item</title></item>
    <item><title>Bad date item</title><pubDate>not-a-date</pubDate></item>
    </channel></rss>"""
    items = fed_mod._parse("testimony", rss)
    assert items[0]["published"] is None
    assert items[1]["published"] is None


def test_fetch_returns_empty_on_http_failure(monkeypatch):
    monkeypatch.setattr(
        fed_mod.requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(_req.ConnectionError()),
    )
    with (
        patch(
            "apps.market.services.fed.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        assert fed_mod.fetch_fed_communications() == []


def test_dtd_and_entity_declarations_rejected():
    evil = b"<?xml version='1.0'?><!DOCTYPE r [<!ENTITY a 'x'>]><rss><channel/></rss>"
    with pytest.raises(ValueError, match="DTD/entity"):
        fed_mod._parse("speeches", evil)


def test_size_cap_rejects_oversized_feed(monkeypatch):
    class _Resp:
        raw = type("R", (), {"read": staticmethod(lambda n, decode_content=True: b"x" * n)})()

        def raise_for_status(self):
            pass

    monkeypatch.setattr(fed_mod.requests, "get", lambda *a, **k: _Resp())
    with (
        patch(
            "apps.market.services.fed.cache.get_or_fetch",
            side_effect=_PASSTHROUGH_CACHE,
        ),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        assert fed_mod.fetch_fed_communications() == []  # oversized -> [] (never raises)


def test_fetch_fed_communications_mock_mode():
    """Mock mode short-circuits the network entirely; canned items are well-formed."""
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        items = fed_mod.fetch_fed_communications()

    assert items
    for item in items:
        assert set(item) == {"kind", "title", "url", "published", "summary"}


def test_fetch_fed_communications_merges_feeds_newest_first():
    """Across all configured feeds, results are sorted newest-first and limited."""
    older = [
        {
            "kind": "speeches",
            "title": "Older speech",
            "url": "https://www.federalreserve.gov/a.htm",
            "published": "2026-09-01T00:00:00+00:00",
            "summary": "",
        }
    ]
    newer = [
        {
            "kind": "press_monetary",
            "title": "Newer press release",
            "url": "https://www.federalreserve.gov/b.htm",
            "published": "2026-09-16T18:00:00+00:00",
            "summary": "",
        }
    ]

    def _fake_fetch_feed(kind, url):
        return newer if kind == "press_monetary" else older

    with (
        patch("apps.market.services.fed._fetch_feed", side_effect=_fake_fetch_feed),
        patch("apps.core.mocks.is_mock_mode", return_value=False),
    ):
        items = fed_mod.fetch_fed_communications(limit=1)

    assert items == newer


def test_fetch_feed_returns_empty_and_logs_on_cache_error(monkeypatch, caplog):
    """A cache/Redis failure never propagates — the section must degrade to []."""
    with patch(
        "apps.market.services.fed.cache.get_or_fetch",
        side_effect=OSError("redis gone"),
    ):
        assert fed_mod._fetch_feed("speeches", "https://example.invalid/x.xml") == []
