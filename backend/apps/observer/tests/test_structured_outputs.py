"""Observer structured mode writes a typed ObservationReport JSON into the
thread so the UI can render cards instead of parsing markdown."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.observer.schemas import ObservationReport
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig


@pytest.fixture
def provider_cfg(db) -> ProviderConfig:
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-test"
    cfg.save()
    return cfg


@pytest.fixture
def schedule_structured(db, provider_cfg):
    from apps.observer.models import ObserverSchedule

    profile = TradingProfile.objects.create(
        name="p",
        style="s",
        default_provider="claude",
    )
    return ObserverSchedule.objects.create(
        name="sched",
        profile=profile,
        objective_template="watch",
        structured=True,
        market_hours_only=False,
    )


@pytest.fixture
def fake_report() -> ObservationReport:
    return ObservationReport(
        headline="SPY grinds toward 525 with light vol",
        bias="neutral",
        summary="Price respects the rising 20-period but breadth is mixed.",
        signals=[],
        key_levels=[],
        risks=["CPI tomorrow"],
        next_check_in="after the 10:00 breadth reading",
    )


def test_structured_observer_run_persists_parsed_json(
    db,
    schedule_structured,
    fake_report,
) -> None:
    from apps.observer.services import run as run_service

    with (
        patch.object(run_service, "run_structured", return_value=fake_report),
        patch.object(run_service.run_ai_on_message, "delay") as streaming,
    ):
        run_service.run_observer(schedule_structured.id)

    streaming.assert_not_called()
    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import Message

    thread = get_or_create_observer_thread(schedule_structured.profile)
    msg = Message.objects.filter(thread=thread, role="assistant").order_by("-id").first()
    assert msg is not None
    assert msg.content["kind"] == "structured_observation"
    assert msg.content["report"]["headline"] == fake_report.headline
    assert msg.content["report"]["bias"] == "neutral"
