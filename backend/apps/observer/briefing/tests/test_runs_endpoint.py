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
def test_list_returns_runs(api):
    BriefingRun.objects.create(status="ready", data={})
    BriefingRun.objects.create(status="ready", data={})
    r = api.get("/api/briefings/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list) and len(body) == 2
