import pytest

from apps.profiles.models import Watchlist, WatchlistSymbol


@pytest.mark.django_db
def test_unique_symbol_per_watchlist():
    w = Watchlist.objects.create(name="A")
    WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=0)
    with pytest.raises(Exception, match=""):
        WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=1)


@pytest.mark.django_db
def test_ticker_is_stripped():
    w = Watchlist.objects.create(name="A")
    s = WatchlistSymbol.objects.create(watchlist=w, ticker=" nvda ", sort_order=0)
    s.refresh_from_db()
    assert s.ticker == "NVDA"
