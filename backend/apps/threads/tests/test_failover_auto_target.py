"""Failover with no secondary named picks one itself.

`ai_failover_provider` defaults to "", so without an auto-resolver the toggle is
enabled-but-inert: `_failover_target` returns None and nothing ever fails over.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from apps.secrets.models import ProviderConfig
from apps.threads.tasks import _failover_target


@pytest.fixture
def enabled_no_secondary():
    with override_settings(AI_FAILOVER_ENABLED=True, AI_FAILOVER_PROVIDER=""):
        yield


@pytest.mark.django_db
def test_auto_picks_the_first_other_usable_provider(enabled_no_secondary):
    ProviderConfig.objects.create(provider="claude", api_key="sk-a", default_model="claude-opus-5")
    ProviderConfig.objects.create(provider="openai", api_key="sk-b", default_model="gpt-5")

    target = _failover_target("claude")

    assert target is not None
    name, model, cfg = target
    assert (name, model) == ("openai", "gpt-5")
    assert cfg.provider == "openai"


@pytest.mark.django_db
def test_auto_never_returns_the_primary(enabled_no_secondary):
    ProviderConfig.objects.create(provider="claude", api_key="sk-a", default_model="claude-opus-5")

    assert _failover_target("claude") is None


@pytest.mark.django_db
def test_auto_skips_a_provider_with_no_credential(enabled_no_secondary):
    ProviderConfig.objects.create(provider="claude", api_key="sk-a", default_model="claude-opus-5")
    # A row with a model but no key can't serve a retry.
    ProviderConfig.objects.create(provider="openai", default_model="gpt-5")

    assert _failover_target("claude") is None


@pytest.mark.django_db
def test_auto_skips_a_disabled_provider(enabled_no_secondary):
    ProviderConfig.objects.create(provider="claude", api_key="sk-a", default_model="claude-opus-5")
    ProviderConfig.objects.create(
        provider="openai", api_key="sk-b", default_model="gpt-5", enabled=False
    )

    assert _failover_target("claude") is None


@pytest.mark.django_db
def test_auto_accepts_a_local_endpoint_without_a_key(enabled_no_secondary):
    ProviderConfig.objects.create(provider="claude", api_key="sk-a", default_model="claude-opus-5")
    ProviderConfig.objects.create(
        provider="local",
        base_url="http://host.docker.internal:11434/v1",
        default_model="local-7b",
    )

    target = _failover_target("claude")
    assert target is not None
    assert target[0] == "local"


@pytest.mark.django_db
def test_auto_is_off_when_failover_is_off():
    ProviderConfig.objects.create(provider="openai", api_key="sk-b", default_model="gpt-5")
    with override_settings(AI_FAILOVER_ENABLED=False, AI_FAILOVER_PROVIDER=""):
        assert _failover_target("claude") is None
