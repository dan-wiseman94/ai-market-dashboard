from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.market.models import MarketEvent
from apps.market.tasks import refresh_events
from apps.profiles.models import Watchlist, WatchlistSymbol


@pytest.mark.django_db
def test_refresh_events_pulls_watchlist_tickers_and_prunes_old():
    wl = Watchlist.objects.create(name="Core")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="NVDA")
    MarketEvent.objects.create(  # stale -> pruned
        source="finnhub",
        external_id="EARN:OLD:1",
        kind="earnings",
        ticker="OLD",
        title="OLD earnings",
        event_time=timezone.now() - timedelta(days=40),
    )
    with (
        patch("apps.market.tasks.events_service.fetch_earnings", return_value=[1, 2]) as fe,
        patch("apps.market.tasks.events_service.fetch_macro", return_value=[1]) as fm,
    ):
        result = refresh_events()

    fe.assert_called_once()
    assert "NVDA" in fe.call_args.args[0]
    fm.assert_called_once()
    assert result == {"earnings": 2, "macro": 1, "pruned": 1}
    assert not MarketEvent.objects.filter(external_id="EARN:OLD:1").exists()
