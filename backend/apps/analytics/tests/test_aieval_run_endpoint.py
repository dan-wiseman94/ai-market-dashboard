"""POST /api/aieval/runs/ — the three behaviours layered on top of the shipped
provider-aware endpoint (whose own contract is covered by test_aieval_manual_run).

The harness bills one model call per replayed row, so the endpoint refuses BEFORE
queueing rather than after: MOCK_EXTERNAL is a refusal because run_structured
hands back a canned report, which would persist as a fabricated measurement the
coach and the calibration-weighted router then trust.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.core.models import SystemSettings
from apps.secrets.models import ProviderConfig

pytestmark = pytest.mark.django_db


@pytest.fixture
def claude_cfg():
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


def test_mock_mode_refuses_without_queueing(claude_cfg, monkeypatch):
    monkeypatch.setenv("MOCK_EXTERNAL", "true")

    with patch("apps.analytics.aieval_views.aieval_run") as task:
        resp = APIClient().post("/api/aieval/runs/", {}, format="json")

    assert resp.status_code == 409
    assert resp.json()["code"] == "mock_mode"
    task.delay.assert_not_called()


def test_explicit_null_horizon_means_every_horizon(claude_cfg):
    with patch("apps.analytics.aieval_views.aieval_run") as task:
        resp = APIClient().post("/api/aieval/runs/", {"horizon": None}, format="json")

    assert resp.status_code == 202
    assert resp.json()["horizon"] is None
    assert task.delay.call_args.kwargs["horizon"] is None


def test_system_settings_defaults_beat_the_env_defaults(claude_cfg):
    # The horizon and limit knobs are UI-editable; a run queued with an empty body
    # must honour them rather than a constant baked into the serializer.
    SystemSettings.objects.update_or_create(
        pk=1, defaults={"aieval_scheduled_limit": 3, "aieval_scheduled_horizon": 90}
    )

    with patch("apps.analytics.aieval_views.aieval_run") as task:
        resp = APIClient().post("/api/aieval/runs/", {}, format="json")

    assert resp.status_code == 202
    assert task.delay.call_args.kwargs["limit"] == 3
    assert task.delay.call_args.kwargs["horizon"] == 90


def test_a_system_prompt_override_reaches_the_task_only_when_given(claude_cfg):
    with patch("apps.analytics.aieval_views.aieval_run") as task:
        APIClient().post("/api/aieval/runs/", {"system": "be terse"}, format="json")
    assert task.delay.call_args.kwargs["system"] == "be terse"

    with patch("apps.analytics.aieval_views.aieval_run") as task:
        APIClient().post("/api/aieval/runs/", {}, format="json")
    assert "system" not in task.delay.call_args.kwargs
