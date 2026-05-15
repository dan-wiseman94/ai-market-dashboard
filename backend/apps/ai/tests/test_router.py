import pytest

from apps.ai.router import ResolutionError, resolve_provider_and_model
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.threads.models import Thread


@pytest.mark.django_db
def test_resolves_from_profile_default():
    p = TradingProfile.objects.create(
        name="P",
        style="x",
        default_provider="openai",
        default_model="gpt-5-mini",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    ProviderConfig.objects.create(provider="openai", default_model="gpt-5")

    resolved = resolve_provider_and_model(thread=t, message=None, override=None)
    assert resolved == ("openai", "gpt-5-mini")


@pytest.mark.django_db
def test_override_wins_over_profile():
    p = TradingProfile.objects.create(
        name="P",
        style="x",
        default_provider="openai",
        default_model="gpt-5-mini",
    )
    t = Thread.objects.create(kind="chat", profile=p, title="x")
    ProviderConfig.objects.create(provider="claude")
    ProviderConfig.objects.create(provider="openai")

    resolved = resolve_provider_and_model(
        thread=t,
        message=None,
        override={"provider": "claude", "model": "claude-opus-4-7"},
    )
    assert resolved == ("claude", "claude-opus-4-7")


@pytest.mark.django_db
def test_falls_back_to_providerconfig_when_no_profile():
    t = Thread.objects.create(kind="chat", profile=None, title="x")
    ProviderConfig.objects.create(provider="claude", default_model="claude-haiku-4-5-20251001")

    resolved = resolve_provider_and_model(thread=t, message=None, override=None)
    assert resolved == ("claude", "claude-haiku-4-5-20251001")


@pytest.mark.django_db
def test_no_providers_configured_raises():
    t = Thread.objects.create(kind="chat", profile=None, title="x")

    with pytest.raises(ResolutionError):
        resolve_provider_and_model(thread=t, message=None, override=None)
