"""One model id per fire: the prompt hash, the structured call and the ledger
stamp all read the same resolution, and a catalog id owned by another provider
is never sent."""

from __future__ import annotations

import pytest

from apps.observer.models import ObserverSchedule
from apps.observer.services.run import _observer_model
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig


@pytest.fixture
def profile(db) -> TradingProfile:
    return TradingProfile.objects.create(
        name="P", style="s", default_provider="claude", default_model="claude-sonnet-5"
    )


def _sched(profile: TradingProfile, **kw) -> ObserverSchedule:
    return ObserverSchedule(name="S", profile=profile, **kw)


@pytest.mark.django_db
def test_override_model_wins(profile):
    cfg = ProviderConfig(provider="claude", default_model="claude-opus-5")
    sched = _sched(profile, override_model="claude-fable-5-1")
    assert _observer_model(sched, cfg, "claude") == "claude-fable-5-1"


@pytest.mark.django_db
def test_profile_model_used_on_the_profiles_own_provider(profile):
    cfg = ProviderConfig(provider="claude", default_model="claude-opus-5")
    assert _observer_model(_sched(profile), cfg, "claude") == "claude-sonnet-5"


@pytest.mark.django_db
def test_profile_model_skipped_when_schedule_overrides_the_provider(profile):
    cfg = ProviderConfig(provider="openai", default_model="")
    sched = _sched(profile, override_provider="openai")
    assert _observer_model(sched, cfg, "openai") == "gpt-5.6-sol"


@pytest.mark.django_db
def test_foreign_override_model_is_skipped_not_sent(profile):
    cfg = ProviderConfig(provider="openai", default_model="gpt-5")
    sched = _sched(profile, override_provider="openai", override_model="claude-opus-5")
    assert _observer_model(sched, cfg, "openai") == "gpt-5"


@pytest.mark.django_db
def test_config_default_then_catalog_default(profile):
    profile.default_model = ""
    cfg_with_model = ProviderConfig(provider="claude", default_model="claude-opus-4-8")
    assert _observer_model(_sched(profile), cfg_with_model, "claude") == "claude-opus-4-8"
    cfg_blank = ProviderConfig(provider="claude", default_model="")
    assert _observer_model(_sched(profile), cfg_blank, "claude") == "claude-opus-5"
    assert _observer_model(_sched(profile), None, "claude") == "claude-opus-5"


@pytest.mark.django_db
def test_plain_fire_sends_the_resolved_pair_as_the_override(profile):
    """The router honours an override only when BOTH provider and model are present, so
    a schedule with a provider override and no model would otherwise silently run on
    the profile's provider."""
    from unittest.mock import patch

    from apps.observer.services import run as run_service
    from apps.secrets.models import ProviderConfig

    cfg = ProviderConfig.objects.create(
        provider="openai", enabled=True, default_model="gpt-5.6-sol"
    )
    cfg.api_key = "sk-oai"
    cfg.save()
    sched = ObserverSchedule.objects.create(
        name="S",
        profile=profile,
        market_hours_only=False,
        override_provider="openai",  # provider only: no override_model
    )

    with (
        patch.object(run_service, "any_market_open", return_value=True),
        patch.object(run_service, "check_daily_cap"),
        patch.object(run_service, "check_monthly_cap"),
        patch.object(run_service, "capture") as capture,
        patch.object(run_service, "serialize_for_ai", return_value="## BODY"),
        patch.object(run_service, "assemble_coach_context", return_value=""),
        patch.object(run_service, "notify"),
        patch.object(run_service.run_ai_on_message, "delay") as streaming,
    ):
        from apps.snapshots.models import Snapshot

        capture.return_value = Snapshot.objects.create(
            profile=profile, includes=["quotes"], source="observer", status="ready"
        )
        run_service.fire_observer(sched.id)

    override = streaming.call_args.kwargs["override"]
    assert override == {"provider": "openai", "model": "gpt-5.6-sol"}


@pytest.mark.django_db
def test_local_provider_falls_through_to_the_configs_own_model(profile):
    # `local` has no catalog default, so a blank config default yields "".
    cfg = ProviderConfig(provider="local", default_model="llama-3.1-70b")
    sched = _sched(profile, override_provider="local")
    assert _observer_model(sched, cfg, "local") == "llama-3.1-70b"
    assert _observer_model(sched, ProviderConfig(provider="local"), "local") == ""
