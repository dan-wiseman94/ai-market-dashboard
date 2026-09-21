"""POST /api/aieval/runs/ — queue an eval run from the UI.

The harness bills one model call per replayed row, so the endpoint refuses BEFORE
queueing rather than after. Two refusals, each with its own non-5xx status so the
UI can say why: MOCK_EXTERNAL (run_structured hands back a canned report, which
would persist as a fabricated measurement the coach and the calibration-weighted
router then trust) and a breached provider cost cap.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from rest_framework.test import APIClient

from apps.analytics import tasks as analytics_tasks
from apps.analytics.models import EvalRun
from apps.core.models import SystemSettings
from apps.secrets.models import ProviderConfig
from apps.threads.models import AIRun

pytestmark = pytest.mark.django_db


@pytest.fixture
def delay(monkeypatch):
    """Intercept the enqueue — no test may put a billing task on the real broker."""
    m = MagicMock(return_value=MagicMock(id="task-123"))
    monkeypatch.setattr(analytics_tasks.run_manual, "delay", m)
    return m


@pytest.fixture(autouse=True)
def _eval_defaults(settings):
    settings.AIEVAL_SCHEDULED_MODEL = "claude-sonnet-4-6"
    settings.AIEVAL_SCHEDULED_HORIZON = 30
    settings.AIEVAL_SCHEDULED_LIMIT = 25


def test_empty_body_defaults_from_runtime_config(delay):
    resp = APIClient().post("/api/aieval/runs/", {}, format="json")

    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    assert delay.call_args.kwargs == {
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "horizon": 30,
        "limit": 25,
        "label": "manual",
        "system": None,
    }


def test_system_settings_override_beats_the_env_default(delay):
    # The knob is UI-editable; a run queued from the UI must honour it.
    SystemSettings.objects.update_or_create(pk=1, defaults={"aieval_scheduled_limit": 3})

    APIClient().post("/api/aieval/runs/", {}, format="json")

    assert delay.call_args.kwargs["limit"] == 3


def test_body_overrides_every_default(delay):
    resp = APIClient().post(
        "/api/aieval/runs/",
        {
            "provider": "openai",
            "horizon": 7,
            "limit": 5,
            "label": "variant-b",
            "system": "be terse",
        },
        format="json",
    )

    assert resp.status_code == 202
    kwargs = delay.call_args.kwargs
    assert kwargs["provider"] == "openai"
    assert kwargs["horizon"] == 7
    assert kwargs["limit"] == 5
    assert kwargs["label"] == "variant-b"
    assert kwargs["system"] == "be terse"


def test_claude_default_model_is_not_sent_to_openai(delay):
    # The only configured eval model is a Claude catalog row; asking for OpenAI must
    # resolve OpenAI's own default instead of skipping every row on a bad model id.
    APIClient().post("/api/aieval/runs/", {"provider": "openai"}, format="json")

    model = delay.call_args.kwargs["model"]
    assert model != "claude-sonnet-4-6"
    assert not model.startswith("claude")


def test_explicit_null_horizon_means_every_horizon(delay):
    APIClient().post("/api/aieval/runs/", {"horizon": None}, format="json")

    assert delay.call_args.kwargs["horizon"] is None


def test_local_provider_requires_an_explicit_model(delay):
    resp = APIClient().post("/api/aieval/runs/", {"provider": "local"}, format="json")

    assert resp.status_code == 400
    assert "model" in resp.json()
    delay.assert_not_called()


def test_limit_is_bounded(delay):
    resp = APIClient().post("/api/aieval/runs/", {"limit": 5000}, format="json")

    assert resp.status_code == 400
    delay.assert_not_called()


def test_mock_mode_refuses_without_queueing(delay, monkeypatch):
    monkeypatch.setenv("MOCK_EXTERNAL", "true")

    resp = APIClient().post("/api/aieval/runs/", {}, format="json")

    assert resp.status_code == 409
    delay.assert_not_called()


def test_breached_cost_cap_refuses_without_queueing(delay):
    ProviderConfig.objects.create(provider="claude", daily_cost_cap_usd=Decimal("1.00"))
    AIRun.objects.create(provider="claude", model="claude-sonnet-4-6", cost_usd=Decimal("2.00"))

    resp = APIClient().post("/api/aieval/runs/", {}, format="json")

    assert resp.status_code == 429
    assert "daily cap" in resp.json()["detail"]
    delay.assert_not_called()


def test_list_still_reads_and_exposes_the_provider():
    EvalRun.objects.create(provider="openai", model="gpt-5-nano", n=1)

    body = APIClient().get("/api/aieval/runs/").json()

    assert body[0]["provider"] == "openai"
