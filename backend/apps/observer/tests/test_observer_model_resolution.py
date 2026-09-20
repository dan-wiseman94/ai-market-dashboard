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
def test_local_provider_falls_through_to_the_configs_own_model(profile):
    # `local` has no catalog default, so a blank config default yields "".
    cfg = ProviderConfig(provider="local", default_model="llama-3.1-70b")
    sched = _sched(profile, override_provider="local")
    assert _observer_model(sched, cfg, "local") == "llama-3.1-70b"
    assert _observer_model(sched, ProviderConfig(provider="local"), "local") == ""
