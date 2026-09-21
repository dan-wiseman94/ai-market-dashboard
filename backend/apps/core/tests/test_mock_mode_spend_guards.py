"""Beat tasks that bill a provider must refuse under MOCK_EXTERNAL.

The e2e overlay sets MOCK_EXTERNAL=true and runs a real `beat` service, and every
product flag now ships ON — so any scheduled task that reaches a provider would spend
real money on every CI run. The AI clients' own mock short-circuit does NOT cover
these: they go through ``apps.ai.structured.run_structured``, which has none.

Their user-initiated siblings are deliberately NOT gated — a manual click is explicit
intent, and the manual eval path (`manage.py aieval`) calls ``evaluate()`` directly
rather than going through the beat task at all.
"""

from unittest.mock import patch

import pytest
from django.test import override_settings


@override_settings(AIEVAL_SCHEDULED_ENABLED=True)
def test_scheduled_eval_refuses_under_mock_mode():
    from apps.analytics.tasks import run_scheduled

    with (
        patch("apps.core.mocks.is_mock_mode", return_value=True),
        patch("apps.analytics.tasks.evaluate") as evaluate,
        patch("apps.analytics.tasks.preflight_cost_cap") as preflight,
    ):
        assert run_scheduled() == {"skipped": "mock_mode"}

    evaluate.assert_not_called()
    preflight.assert_not_called()


@pytest.mark.django_db
@override_settings(AIEVAL_SCHEDULED_ENABLED=True)
def test_scheduled_eval_still_runs_when_not_mocked():
    from apps.analytics.tasks import run_scheduled

    with (
        patch("apps.core.mocks.is_mock_mode", return_value=False),
        patch("apps.analytics.tasks.preflight_cost_cap"),
        patch("apps.analytics.tasks.evaluate", return_value={"n": 0}) as evaluate,
    ):
        assert run_scheduled() == {"skipped": "no_data"}

    evaluate.assert_called_once()


@override_settings(ANOMALY_SWEEP_ENABLED=True)
def test_anomaly_sweep_refuses_under_mock_mode():
    from apps.strategy.tasks import sweep

    with (
        patch("apps.core.mocks.is_mock_mode", return_value=True),
        patch("apps.strategy.tasks.run_sweep") as run_sweep,
    ):
        assert sweep() is None

    run_sweep.assert_not_called()


@pytest.mark.django_db  # past the mock guard the task resolves the runtime knob
@override_settings(ANOMALY_SWEEP_ENABLED=True)
def test_anomaly_sweep_still_runs_when_not_mocked():
    from apps.strategy.tasks import sweep

    with (
        patch("apps.core.mocks.is_mock_mode", return_value=False),
        patch("apps.strategy.tasks.run_sweep", return_value=3) as run_sweep,
    ):
        assert sweep() == 3

    run_sweep.assert_called_once()


@override_settings(ANOMALY_SWEEP_ENABLED=False)
def test_manual_sweep_is_not_gated_by_mock_mode():
    """sweep_now is the user's own click — it runs regardless of the flag AND of
    MOCK_EXTERNAL, so the e2e UI journey that presses the button still exercises it."""
    from apps.strategy.tasks import sweep_now

    with (
        patch("apps.core.mocks.is_mock_mode", return_value=True),
        patch("apps.strategy.tasks.run_sweep", return_value=1) as run_sweep,
    ):
        assert sweep_now() == 1

    run_sweep.assert_called_once()
