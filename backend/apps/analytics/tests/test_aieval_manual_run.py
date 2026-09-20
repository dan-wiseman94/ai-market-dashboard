"""POST /api/aieval/runs/ — a manual, bounded, billed eval run on any provider."""

from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.test import APIClient

from apps.ai.cost import CostCapExceededError
from apps.analytics.models import EvalRun
from apps.secrets.models import ProviderConfig


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def openai_cfg(db):
    cfg = ProviderConfig.objects.create(provider="openai", default_model="gpt-5.6-sol")
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


@pytest.mark.django_db
def test_post_queues_the_task_with_resolved_defaults(api, openai_cfg):
    with patch("apps.analytics.aieval_views.aieval_run") as task:
        r = api.post("/api/aieval/runs/", {"provider": "openai"}, format="json")

    assert r.status_code == 202
    assert r.json() == {
        "queued": True,
        "provider": "openai",
        "model": "gpt-5.6-sol",
        "horizon": 30,
        "limit": 25,
        "label": "manual",
    }
    task.delay.assert_called_once_with(
        provider="openai", model="gpt-5.6-sol", horizon=30, limit=25, label="manual"
    )


@pytest.mark.django_db
def test_post_rejects_an_unknown_provider_and_a_foreign_model(api, openai_cfg):
    bad = api.post("/api/aieval/runs/", {"provider": "gemini"}, format="json")
    assert bad.status_code == 400
    # One error shape for the endpoint, so the UI always has a message to show.
    assert bad.json()["code"] == "invalid_request"
    assert "provider" in bad.json()["message"]
    r = api.post(
        "/api/aieval/runs/", {"provider": "openai", "model": "claude-opus-5"}, format="json"
    )
    assert r.status_code == 400
    assert r.json()["code"] == "foreign_model"


@pytest.mark.django_db
def test_post_queues_the_resolved_model_for_a_local_provider(api):
    """`local` has no catalog default, so the queued model must come from the provider's
    own config — queueing the request's blank id would run the eval against no model."""
    ProviderConfig.objects.create(
        provider="local",
        enabled=True,
        base_url="http://host.docker.internal:11434/v1",
        default_model="llama-3.1-70b",
    )
    with patch("apps.analytics.aieval_views.aieval_run") as task:
        r = api.post("/api/aieval/runs/", {"provider": "local"}, format="json")

    assert r.status_code == 202
    assert r.json()["model"] == "llama-3.1-70b"
    assert task.delay.call_args.kwargs["model"] == "llama-3.1-70b"


@pytest.mark.django_db
def test_post_400_when_no_model_can_be_resolved(api):
    """A local endpoint with no default model resolves to no target at all — refuse
    rather than queue a run that would replay every row against an empty model id."""
    ProviderConfig.objects.create(
        provider="local", enabled=True, base_url="http://x:11434/v1", default_model=""
    )
    r = api.post("/api/aieval/runs/", {"provider": "local"}, format="json")
    assert r.status_code == 400
    assert r.json()["code"] == "no_provider"


@pytest.mark.django_db
def test_post_400_when_the_provider_has_no_credential(api):
    ProviderConfig.objects.create(provider="openai")  # enabled, no key
    r = api.post("/api/aieval/runs/", {"provider": "openai"}, format="json")
    assert r.status_code == 400
    assert r.json()["code"] == "no_provider"


@pytest.mark.django_db
def test_post_409_when_the_cap_is_already_exceeded(api, openai_cfg):
    with patch(
        "apps.analytics.aieval_views.ensure_within_caps",
        side_effect=CostCapExceededError("daily cap hit"),
    ):
        r = api.post("/api/aieval/runs/", {"provider": "openai"}, format="json")
    assert r.status_code == 409
    assert r.json()["code"] == "cost_cap"


@pytest.mark.django_db
@override_settings(THESIS_POSTMORTEM_HORIZONS=[7, 30, 90])
def test_post_validates_horizon_limit_and_label(api, openai_cfg):
    bad_h = api.post("/api/aieval/runs/", {"provider": "openai", "horizon": 12}, format="json")
    assert bad_h.status_code == 400
    bad_l = api.post("/api/aieval/runs/", {"provider": "openai", "limit": 500}, format="json")
    assert bad_l.status_code == 400
    with patch("apps.analytics.aieval_views.aieval_run") as task:
        ok = api.post(
            "/api/aieval/runs/",
            {"provider": "openai", "horizon": 90, "limit": 3, "label": "ab-openai"},
            format="json",
        )
    assert ok.status_code == 202
    assert task.delay.call_args.kwargs["label"] == "ab-openai"
    assert task.delay.call_args.kwargs["horizon"] == 90


def test_task_is_at_most_once():
    """It bills a provider and is not idempotent — a redelivery would double-charge."""
    from apps.analytics.tasks import aieval_run

    assert aieval_run.acks_late is False


@pytest.mark.django_db
def test_task_persists_the_run_with_its_provider_and_notifies():
    from apps.analytics import tasks
    from apps.observer.models import Notification

    result = {
        "model": "gpt-5.6-sol",
        "provider": "openai",
        "label": "manual",
        "horizon": 30,
        "n": 2,
        "skipped": 0,
        "scored": 2,
        "hit_rate": 0.5,
        "brier": 0.25,
        "avg_confidence": 0.7,
        "calibration_error": 0.1,
        "calibration": [],
        "examples": [],
    }
    with (
        patch.object(tasks, "preflight_cost_cap"),
        patch.object(tasks, "evaluate", return_value=result),
    ):
        out = tasks.aieval_run(
            provider="openai", model="gpt-5.6-sol", horizon=30, limit=25, label="manual"
        )

    run = EvalRun.objects.get(id=out["ran"])
    assert run.provider == "openai"
    assert run.source == "manual"
    assert Notification.objects.filter(kind="eval_done").exists()


@pytest.mark.django_db
def test_task_notifies_when_there_is_nothing_to_replay():
    from apps.analytics import tasks
    from apps.observer.models import Notification

    with (
        patch.object(tasks, "preflight_cost_cap"),
        patch.object(tasks, "evaluate", return_value={"n": 0}),
    ):
        out = tasks.aieval_run(provider="claude", model="claude-opus-5", horizon=30, limit=25)

    assert out == {"skipped": "no_data"}
    assert EvalRun.objects.count() == 0
    assert Notification.objects.filter(kind="eval_done").exists()


@pytest.mark.django_db
def test_list_endpoint_exposes_the_provider(api):
    EvalRun.objects.create(model="gpt-5.6-sol", provider="openai", label="x")
    r = api.get("/api/aieval/runs/")
    assert r.status_code == 200
    assert r.json()[0]["provider"] == "openai"
