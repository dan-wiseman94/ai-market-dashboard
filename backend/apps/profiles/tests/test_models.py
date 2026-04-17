import pytest

from apps.profiles.models import Watchlist, WatchlistSymbol


@pytest.mark.django_db
def test_create_watchlist_with_symbols():
    w = Watchlist.objects.create(name="My Scalps")
    WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=0)
    WatchlistSymbol.objects.create(watchlist=w, ticker="QQQ", sort_order=1)
    assert list(w.symbols.order_by("sort_order").values_list("ticker", flat=True)) == ["SPY", "QQQ"]


@pytest.mark.django_db
def test_unique_symbol_per_watchlist():
    w = Watchlist.objects.create(name="A")
    WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=0)
    with pytest.raises(Exception):
        WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=1)


@pytest.mark.django_db
def test_ticker_is_uppercased():
    w = Watchlist.objects.create(name="A")
    s = WatchlistSymbol.objects.create(watchlist=w, ticker="nvda", sort_order=0)
    s.refresh_from_db()
    assert s.ticker == "NVDA"
