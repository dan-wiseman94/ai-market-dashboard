import pytest
from rest_framework.test import APIClient

from apps.profiles.models import Watchlist, WatchlistSymbol


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_list_create_watchlist(api):
    assert api.get("/api/watchlists/").json() == []

    resp = api.post("/api/watchlists/", {"name": "Scalps"}, format="json")
    assert resp.status_code == 201
    wid = resp.json()["id"]

    data = api.get("/api/watchlists/").json()
    assert len(data) == 1
    assert data[0]["name"] == "Scalps"
    assert data[0]["id"] == wid


@pytest.mark.django_db
def test_rename_and_delete_watchlist(api):
    w = Watchlist.objects.create(name="A")
    api.patch(f"/api/watchlists/{w.id}/", {"name": "B"}, format="json")
    w.refresh_from_db()
    assert w.name == "B"

    api.delete(f"/api/watchlists/{w.id}/")
    assert not Watchlist.objects.filter(id=w.id).exists()


@pytest.mark.django_db
def test_add_remove_symbol(api):
    w = Watchlist.objects.create(name="A")

    r = api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "spy"}, format="json")
    assert r.status_code == 201
    sid = r.json()["id"]
    assert WatchlistSymbol.objects.get(id=sid).ticker == "SPY"

    r = api.delete(f"/api/watchlists/{w.id}/symbols/{sid}/")
    assert r.status_code == 204
    assert not WatchlistSymbol.objects.filter(id=sid).exists()


@pytest.mark.django_db
def test_reorder_symbols(api):
    w = Watchlist.objects.create(name="A")
    a = WatchlistSymbol.objects.create(watchlist=w, ticker="SPY", sort_order=0)
    b = WatchlistSymbol.objects.create(watchlist=w, ticker="QQQ", sort_order=1)

    r = api.post(f"/api/watchlists/{w.id}/reorder/", {"order": [b.id, a.id]}, format="json")
    assert r.status_code == 200
    a.refresh_from_db()
    b.refresh_from_db()
    assert b.sort_order == 0
    assert a.sort_order == 1


@pytest.mark.django_db
def test_duplicate_symbol_returns_400(api):
    w = Watchlist.objects.create(name="A")
    api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "SPY"}, format="json")
    r = api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "SPY"}, format="json")
    assert r.status_code == 400


@pytest.mark.django_db
def test_add_symbol_strips_whitespace(api):
    w = Watchlist.objects.create(name="A")

    r = api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "nvda "}, format="json")
    assert r.status_code == 201
    assert WatchlistSymbol.objects.get(id=r.json()["id"]).ticker == "NVDA"


@pytest.mark.django_db
def test_padded_symbol_still_hits_duplicate_guard(api):
    w = Watchlist.objects.create(name="A")
    api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "nvda "}, format="json")
    r = api.post(f"/api/watchlists/{w.id}/symbols/", {"ticker": "NVDA"}, format="json")
    assert r.status_code == 400
    assert w.symbols.count() == 1
