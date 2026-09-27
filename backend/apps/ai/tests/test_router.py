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
def test_no_providers_configured_raises():
    t = Thread.objects.create(kind="chat", profile=None, title="x")

    with pytest.raises(ResolutionError):
        resolve_provider_and_model(thread=t, message=None, override=None)


@pytest.mark.django_db
def test_resolves_past_undecryptable_enabled_row():
    """A ProviderConfig whose key can't be decrypted must not crash resolution — router
    needs only provider/default_model, so it defers the encrypted column (key/salt change)."""
    from django.db import connection

    t = Thread.objects.create(kind="chat", profile=None, title="x")
    ProviderConfig.objects.create(provider="claude", default_model="claude-opus-4-8", enabled=True)
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_providerconfig SET api_key = %s WHERE provider = %s",
            [b"not-valid-fernet", "claude"],
        )

    resolved = resolve_provider_and_model(thread=t, message=None, override=None)
    assert resolved == ("claude", "claude-opus-4-8")
