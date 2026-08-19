from __future__ import annotations

import json

import pytest


@pytest.mark.django_db
def test_observer_runs_to_json_shape() -> None:
    from apps.export.serializers import observer_runs_to_json, observer_runs_to_markdown
    from apps.observer.models import ObserverSchedule
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    prof = TradingProfile.objects.create(name="obs-prof", style="swing")
    sched = ObserverSchedule.objects.create(
        name="morning-scan",
        profile=prof,
        enabled=True,
    )
    Thread.objects.create(kind="observer", title="Morning run 1", schedule=sched)
    out = observer_runs_to_json(sched)
    assert out["schedule_id"] == sched.id
    assert len(out["runs"]) == 1
    md = observer_runs_to_markdown(sched)
    assert "# Observer" in md


@pytest.mark.django_db
def test_trigger_to_json_shape() -> None:
    from apps.export.serializers import trigger_to_json
    from apps.observer.models import EventTrigger
    from apps.profiles.models import TradingProfile

    prof = TradingProfile.objects.create(name="swing", style="momentum swing")
    t = EventTrigger.objects.create(
        name="breach",
        profile=prof,
        condition={"leaf": {"metric": "last", "ticker": "AAPL", "op": ">", "value": 200}},
        enabled=True,
    )
    out = trigger_to_json(t)
    assert out["name"] == "breach"
    assert out["condition"]["leaf"]["ticker"] == "AAPL"


@pytest.mark.django_db
def test_profiles_and_watchlists_no_secrets() -> None:
    from apps.export.serializers import profiles_to_json, watchlists_to_json
    from apps.profiles.models import TradingProfile, Watchlist, WatchlistSymbol

    TradingProfile.objects.create(name="p1", style="scalp")
    wl = Watchlist.objects.create(name="tech")
    WatchlistSymbol.objects.create(watchlist=wl, ticker="AAPL")
    out_profiles = profiles_to_json()
    out_watchlists = watchlists_to_json()
    s = json.dumps(out_profiles).lower() + json.dumps(out_watchlists).lower()
    for forbidden in ("api_key", "access_token", "refresh_token"):
        assert forbidden not in s
    assert any(p["name"] == "p1" for p in out_profiles["profiles"])
    assert any(w["name"] == "tech" for w in out_watchlists["watchlists"])
    tech = next(w for w in out_watchlists["watchlists"] if w["name"] == "tech")
    assert "AAPL" in tech["tickers"]
