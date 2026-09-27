from unittest.mock import patch

from apps.snapshots.services import _fetch_news_section


def test_news_section_always_24h_default():
    with patch("apps.snapshots.services.fetch_news", return_value=[{"id": 1}]) as m:
        out = _fetch_news_section(watchlist_tickers=["SPY"])
    m.assert_called_once_with(["SPY"])
    assert out["data"] == {"items": [{"id": 1}]}
    assert "window" not in out["data"]
