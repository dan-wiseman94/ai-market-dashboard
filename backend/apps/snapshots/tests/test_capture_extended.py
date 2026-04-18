from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.models import SnapshotImage
from apps.snapshots.services import capture


@pytest.mark.django_db
def test_capture_with_chain_news_image_sections():
    profile = TradingProfile.objects.create(name="P", style="x")

    fake_chain = {"ticker": "SPY", "underlying_last": "521.30", "expiries": {}}
    fake_news_items = [{"id": 1, "headline": "h", "summary": "", "url": "u",
                        "source": "S", "datetime": 1700000000, "related": "SPY"}]

    def fake_render(ticker, timeframe, bars, *, snapshot_id):
        img = SnapshotImage.objects.create(
            snapshot_id=snapshot_id, kind="server_render",
            data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
            caption=f"{ticker} {timeframe}, {bars} bars",
        )
        return img

    # Patch at consumption site (apps.snapshots.services.*), not source modules:
    # services/__init__.py imports the names at import-time, so the lambdas in _FETCHERS
    # close over the local references — patching the source paths would not intercept them.
    with patch("apps.snapshots.services.fetch_chain", return_value=fake_chain), \
         patch("apps.snapshots.services.fetch_news", return_value=fake_news_items), \
         patch("apps.snapshots.services.render_chart_png", side_effect=fake_render):
        snap = capture(
            profile=profile, objective="o", includes=["chain", "news", "image"],
            watchlist_tickers=["SPY"],
            ohlc_ticker="SPY", ohlc_timeframe="5m", ohlc_bars=60,
        )

    assert snap.status == "ready"
    sec_kinds = {s.kind: s for s in snap.sections.all()}
    assert sec_kinds["chain"].status == "done"
    assert sec_kinds["chain"].payload["ticker"] == "SPY"
    assert sec_kinds["news"].status == "done"
    assert sec_kinds["news"].payload["items"][0]["headline"] == "h"
    assert sec_kinds["image"].status == "done"
    assert len(sec_kinds["image"].payload["image_ids"]) == 1
    assert SnapshotImage.objects.filter(snapshot=snap).count() == 1
