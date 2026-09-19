"""``apps.ai.structured`` — the provider-neutral entry point for one-shot
structured output and the target resolution the callers share."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from cryptography.fernet import InvalidToken
from pydantic import BaseModel

from apps.ai.cost import CostCapExceededError
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig

pytestmark = pytest.mark.django_db


class _Out(BaseModel):
    summary: str


def _kw(**overrides):
    kw = dict(api_key="k", model="m", system="s", user="u", output_model=_Out, base_url="")
    kw.update(overrides)
    return kw


# --- dispatch ---------------------------------------------------------------


@pytest.mark.parametrize("provider", ["claude", "anthropic"])
def test_claude_family_dispatches_to_anthropic_impl(provider):
    from apps.ai import structured

    with (
        patch.object(
            structured.claude_structured, "run_structured", return_value=_Out(summary="c")
        ) as c,
        patch.object(structured.openai_structured, "run_structured") as o,
    ):
        out = structured.run_structured(provider=provider, **_kw())
    assert out.summary == "c"
    o.assert_not_called()
    assert "provider" not in c.call_args.kwargs
    assert c.call_args.kwargs["model"] == "m"


@pytest.mark.parametrize("provider", ["openai", "local"])
def test_openai_compatible_dispatches_with_provider(provider):
    from apps.ai import structured

    with (
        patch.object(structured.claude_structured, "run_structured") as c,
        patch.object(
            structured.openai_structured, "run_structured", return_value=_Out(summary="o")
        ) as o,
    ):
        out = structured.run_structured(provider=provider, **_kw(base_url="http://x/v1"))
    assert out.summary == "o"
    c.assert_not_called()
    assert o.call_args.kwargs["provider"] == provider
    assert o.call_args.kwargs["base_url"] == "http://x/v1"


def test_unknown_provider_raises():
    from apps.ai.structured import run_structured

    with pytest.raises(ValueError, match="Unknown provider"):
        run_structured(provider="bard", **_kw())


def test_reexports():
    from apps.ai import structured
    from apps.ai.providers.claude_structured import StructuredParseError

    assert structured.StructuredParseError is StructuredParseError
    assert callable(structured.token_usage_from_anthropic)
    assert callable(structured.token_usage_from_openai)


# --- resolution -------------------------------------------------------------


def _cfg(provider, *, key="", model="", base_url="", enabled=True):
    cfg = ProviderConfig.objects.create(
        provider=provider, default_model=model, base_url=base_url, enabled=enabled
    )
    if key:
        cfg.api_key = key
        cfg.save()
    return cfg


def test_override_provider_wins_and_uses_override_model():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="claude-opus-5")
    _cfg("openai", key="sk-oai", model="gpt-5")
    t = resolve_structured_target(override_provider="openai", override_model="gpt-6-astra")
    assert t is not None
    assert (t.provider, t.model, t.api_key) == ("openai", "gpt-6-astra", "sk-oai")


def test_override_without_model_falls_back_to_config_then_catalog_default():
    from apps.ai.structured import resolve_structured_target

    _cfg("openai", key="sk-oai", model="gpt-5")
    assert resolve_structured_target(override_provider="openai").model == "gpt-5"

    ProviderConfig.objects.all().delete()
    _cfg("openai", key="sk-oai")
    assert resolve_structured_target(override_provider="openai").model == "gpt-5.6-sol"


def test_profile_defaults_used_when_no_override():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="claude-opus-5")
    _cfg("openai", key="sk-oai", model="gpt-5")
    profile = TradingProfile.objects.create(
        name="p", style="s", default_provider="openai", default_model="gpt-5.6-sol"
    )
    t = resolve_structured_target(profile=profile)
    assert (t.provider, t.model) == ("openai", "gpt-5.6-sol")


def test_profile_provider_without_usable_config_yields_none_no_fallthrough():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="claude-opus-5")
    profile = TradingProfile.objects.create(name="p", style="s", default_provider="openai")
    assert resolve_structured_target(profile=profile) is None


def test_calibration_choice_used_when_enabled(settings):
    from apps.ai.structured import resolve_structured_target

    settings.AI_CALIBRATION_ROUTING_ENABLED = True
    _cfg("claude", key="sk-ant", model="claude-opus-5")
    _cfg("openai", key="sk-oai", model="gpt-5.6-sol")
    with patch("apps.ai.router._calibration_choice", return_value=("openai", "gpt-5.6-sol")):
        t = resolve_structured_target()
    assert (t.provider, t.model) == ("openai", "gpt-5.6-sol")


def test_first_enabled_config_is_the_last_resort():
    from apps.ai.structured import resolve_structured_target

    _cfg("openai", key="sk-oai", model="gpt-5")
    _cfg("claude", key="sk-ant", model="claude-opus-5")
    t = resolve_structured_target()
    assert t.provider == "openai"  # lowest id


def test_disabled_and_keyless_configs_are_unusable():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="m", enabled=False)
    _cfg("openai", model="gpt-5")  # enabled, no key
    assert resolve_structured_target() is None
    assert resolve_structured_target(override_provider="claude") is None
    assert resolve_structured_target(override_provider="openai") is None


def test_local_usable_with_base_url_and_no_key_but_needs_a_model():
    from apps.ai.structured import resolve_structured_target

    _cfg("local", base_url="http://host.docker.internal:11434/v1")
    assert resolve_structured_target(override_provider="local") is None  # no model anywhere

    ProviderConfig.objects.all().delete()
    _cfg("local", base_url="http://host.docker.internal:11434/v1", model="llama3")
    t = resolve_structured_target(override_provider="local")
    assert (t.provider, t.model, t.api_key) == ("local", "llama3", "")

    ProviderConfig.objects.all().delete()
    _cfg("local", model="llama3")  # no base_url
    assert resolve_structured_target(override_provider="local") is None


def test_target_carries_caps():
    from apps.ai.structured import resolve_structured_target

    cfg = _cfg("claude", key="sk-ant", model="m")
    cfg.daily_cost_cap_usd = Decimal("3.00")
    cfg.monthly_cost_cap_usd = Decimal("40.00")
    cfg.save()
    t = resolve_structured_target()
    assert (t.daily_cap, t.monthly_cap) == (Decimal("3.00"), Decimal("40.00"))


def _corrupt_key(provider: str) -> None:
    from django.db import connection

    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_providerconfig SET api_key = %s WHERE provider = %s",
            [b"not-valid-fernet", provider],
        )


def test_single_target_lets_invalid_token_propagate():
    from apps.ai.structured import resolve_structured_target

    _cfg("claude", key="sk-ant", model="m")
    _corrupt_key("claude")
    with pytest.raises(InvalidToken):
        resolve_structured_target(override_provider="claude")


def test_capable_targets_enumerates_every_usable_provider_and_skips_undecryptable():
    from apps.ai.structured import structured_capable_targets

    _cfg("claude", key="sk-ant", model="claude-opus-5")
    _cfg("openai", key="sk-oai")  # model from catalog default
    _cfg("local", base_url="http://x/v1", model="llama3")
    _corrupt_key("claude")

    targets = structured_capable_targets()
    assert [(t.provider, t.model) for t in targets] == [
        ("local", "llama3"),
        ("openai", "gpt-5.6-sol"),
    ]


def test_ensure_within_caps_delegates_to_cost_checks():
    from apps.ai.structured import StructuredTarget, ensure_within_caps

    t = StructuredTarget("openai", "m", "k", "", Decimal("1.00"), None)
    with (
        patch("apps.ai.cost.check_daily_cap") as d,
        patch("apps.ai.cost.check_monthly_cap") as m,
    ):
        ensure_within_caps(t)
    d.assert_called_once_with("openai", cap_usd=Decimal("1.00"))
    m.assert_called_once_with("openai", cap_usd=None)

    with (
        patch("apps.ai.cost.check_daily_cap", side_effect=CostCapExceededError("over")),
        pytest.raises(CostCapExceededError),
    ):
        ensure_within_caps(t)
