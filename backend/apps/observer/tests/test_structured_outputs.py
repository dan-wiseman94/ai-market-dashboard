"""Observer structured mode writes a typed ObservationReport JSON into the
thread so the UI can render cards instead of parsing markdown."""

from __future__ import annotations

from unittest.mock import PropertyMock, patch

import pytest
from cryptography.fernet import InvalidToken

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


def test_structured_undecryptable_key_records_failed_message_without_crashing(
    db,
    schedule_structured,
    provider_cfg,
) -> None:
    """A rotated DJANGO_SECRET_KEY/salt makes the deferred api_key undecryptable; the
    structured branch must degrade to an actionable failed Message (mirroring the
    threads path) rather than letting InvalidToken crash the fire silently."""
    from apps.observer.services import run as run_service
    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import Message

    thread = get_or_create_observer_thread(schedule_structured.profile)
    # provider_cfg was fetched fresh below with the deferred key; simulate an
    # undecryptable token by making the api_key property raise on access.
    cfg = ProviderConfig.objects.filter(provider="claude").defer("_api_key").first()
    with (
        patch.object(
            ProviderConfig, "api_key", new_callable=PropertyMock, side_effect=InvalidToken
        ),
        patch.object(run_service, "run_structured") as run_structured,
    ):
        run_service._run_structured_and_record(
            schedule_structured, thread, "payload", "claude", cfg, snap=None
        )

    run_structured.assert_not_called()
    msg = Message.objects.filter(thread=thread, role="assistant", status="failed").first()
    assert msg is not None
    assert msg.error == "undecryptable_key"
    assert "could not be decrypted" in msg.content["text"]


def test_structured_non_claude_provider_skips_with_visible_message(
    db,
    schedule_structured,
) -> None:
    """Structured output runs through Anthropic messages.parse; a schedule that
    resolves to openai/local must skip with a visible Message instead of sending
    that vendor's key to api.anthropic.com (opaque 401 every fire)."""
    from apps.observer.services import run as run_service
    from apps.observer.services.threads import get_or_create_observer_thread
    from apps.threads.models import Message

    thread = get_or_create_observer_thread(schedule_structured.profile)
    with patch.object(run_service, "run_structured") as run_structured:
        run_service._run_structured_and_record(
            schedule_structured, thread, "payload", "openai", None, snap=None
        )

    run_structured.assert_not_called()
    msg = Message.objects.filter(thread=thread, role="system", status="failed").first()
    assert msg is not None
    assert msg.error == "unsupported_provider"
    assert "Claude" in msg.content["text"]
    # Not a capability_warning kind — those are excluded from the observer
    # timeline, and this skip must stay visible there.
    assert msg.content.get("kind") is None
