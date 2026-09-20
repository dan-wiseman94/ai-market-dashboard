"""Tests for the `fed` snapshot section fetcher (apps.snapshots.services._FETCHERS)."""

from unittest.mock import patch

import apps.snapshots.services as snapshot_services


def test_fed_fetcher_wraps_items_under_data():
    canned = [
        {
            "kind": "press_monetary",
            "title": "FOMC statement",
            "url": "https://www.federalreserve.gov/a.htm",
            "published": "2026-09-16T18:00:00+00:00",
            "summary": "...",
        }
    ]
    with patch.object(snapshot_services, "fetch_fed_communications", return_value=canned) as m:
        out = snapshot_services._FETCHERS["fed"]()
    m.assert_called_once_with()
    assert out == {"data": {"items": canned}}


def test_fed_fetcher_empty_feed_returns_empty_items():
    with patch.object(snapshot_services, "fetch_fed_communications", return_value=[]):
        out = snapshot_services._FETCHERS["fed"]()
    assert out == {"data": {"items": []}}
