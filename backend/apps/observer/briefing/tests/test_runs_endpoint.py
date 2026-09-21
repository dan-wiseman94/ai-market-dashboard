import pytest

from apps.observer.models import BriefingRun


@pytest.mark.django_db
def test_latest_returns_most_recent(api):
    BriefingRun.objects.create(status="ready", data={"theses": []})
    newer = BriefingRun.objects.create(status="ready", data={"theses": [{"ticker": "NVDA"}]})
    r = api.get("/api/briefings/latest/")
    assert r.status_code == 200
    assert r.json()["id"] == newer.id
    assert r.json()["data"]["theses"][0]["ticker"] == "NVDA"


@pytest.mark.django_db
def test_latest_empty_returns_204(api):
    r = api.get("/api/briefings/latest/")
    assert r.status_code == 204


@pytest.mark.django_db
def test_run_now_creates_run(api):
    with pytest.MonkeyPatch.context() as mp:
        from apps.observer.briefing import views

        mp.setattr(
            views,
            "run_briefing",
            lambda *, scheduled: BriefingRun.objects.create(status="ready", data={}),
        )
        r = api.post("/api/briefings/run/")
    assert r.status_code == 201
    assert BriefingRun.objects.count() == 1


@pytest.mark.django_db
def test_list_returns_paginated_runs(api):
    oldest = BriefingRun.objects.create(status="ready", data={})
    newest = BriefingRun.objects.create(status="ready", data={})
    r = api.get("/api/briefings/")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 2
    assert [row["id"] for row in body["results"]] == [newest.id, oldest.id]


@pytest.mark.django_db
def test_list_pages_beyond_one_page(api):
    """History is unbounded over time, so the list must page rather than silently
    truncate — a fixed head slice hides every older briefing."""
    for _ in range(3):
        BriefingRun.objects.create(status="ready", data={})
    body = api.get("/api/briefings/?page_size=2").json()
    assert body["count"] == 3
    assert len(body["results"]) == 2
    assert body["next"] is not None
    assert len(api.get("/api/briefings/?page_size=2&page=2").json()["results"]) == 1
