"""The scheduled eval runs on the configured provider, and a model id left over
from another vendor is repaired rather than sent."""

from unittest.mock import patch

import pytest

from apps.core.models import SystemSettings


def _configure(provider: str, model: str) -> None:
    cfg = SystemSettings.load()
    cfg.aieval_scheduled_enabled = True
    cfg.aieval_scheduled_provider = provider
    cfg.aieval_scheduled_model = model
    cfg.save()


@pytest.mark.django_db
def test_run_scheduled_uses_configured_provider_and_repairs_a_foreign_model():
    _configure("openai", "claude-sonnet-4-6")
    from apps.analytics import tasks

    with (
        patch.object(tasks, "preflight_cost_cap") as preflight,
        patch.object(tasks, "evaluate", return_value={"n": 0}) as evaluate,
    ):
        out = tasks.run_scheduled()

    preflight.assert_called_once_with("openai")
    assert evaluate.call_args.kwargs["provider"] == "openai"
    assert evaluate.call_args.kwargs["model"] == "gpt-5.6-sol"
    assert out == {"skipped": "no_data"}


@pytest.mark.django_db
def test_run_scheduled_keeps_a_same_vendor_model():
    _configure("claude", "claude-sonnet-5")
    from apps.analytics import tasks

    with (
        patch.object(tasks, "preflight_cost_cap"),
        patch.object(tasks, "evaluate", return_value={"n": 0}) as evaluate,
    ):
        tasks.run_scheduled()

    assert evaluate.call_args.kwargs["model"] == "claude-sonnet-5"
    assert evaluate.call_args.kwargs["provider"] == "claude"


@pytest.mark.django_db
def test_run_scheduled_cost_cap_is_checked_on_the_configured_provider():
    from apps.ai.cost import CostCapExceededError
    from apps.analytics import tasks

    _configure("openai", "")
    with (
        patch.object(tasks, "preflight_cost_cap", side_effect=CostCapExceededError("over")),
        patch.object(tasks, "evaluate") as evaluate,
    ):
        out = tasks.run_scheduled()

    assert out == {"skipped": "cost_cap"}
    evaluate.assert_not_called()
