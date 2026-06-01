"""Calibration-weighted routing (M14 F2/F6): the opt-in fallback picks the
best-MEASURED enabled model, while per-send override and profile pins still win."""

import pytest

from apps.ai.router import resolve_provider_and_model


def _two_providers_and_evals():
    from apps.aieval.models import EvalRun
    from apps.secrets.models import ProviderConfig

    # claude created first => lower id => the "first enabled" fallback default.
    ProviderConfig.objects.create(provider="claude", enabled=True, default_model="model-a")
    ProviderConfig.objects.create(provider="openai", enabled=True, default_model="model-b")
    EvalRun.objects.create(model="model-a", scored=10, hit_rate=0.5)
    EvalRun.objects.create(model="model-b", scored=10, hit_rate=0.8)  # better


def _unpinned_thread():
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    prof = TradingProfile.objects.create(name="p", style="x", default_provider="", default_model="")
    return Thread.objects.create(kind="chat", profile=prof)


@pytest.mark.django_db
def test_calibration_routing_picks_best_measured(settings):
    settings.AI_CALIBRATION_ROUTING_ENABLED = True
    settings.AI_CALIBRATION_ROUTING_MIN_SCORED = 5
    _two_providers_and_evals()
    assert resolve_provider_and_model(thread=_unpinned_thread()) == ("openai", "model-b")


@pytest.mark.django_db
def test_calibration_off_uses_first_enabled(settings):
    settings.AI_CALIBRATION_ROUTING_ENABLED = False
    _two_providers_and_evals()
    assert resolve_provider_and_model(thread=_unpinned_thread()) == ("claude", "model-a")


@pytest.mark.django_db
def test_override_beats_calibration(settings):
    settings.AI_CALIBRATION_ROUTING_ENABLED = True
    _two_providers_and_evals()
    out = resolve_provider_and_model(
        thread=_unpinned_thread(), override={"provider": "x", "model": "y"}
    )
    assert out == ("x", "y")


@pytest.mark.django_db
def test_profile_pin_beats_calibration(settings):
    settings.AI_CALIBRATION_ROUTING_ENABLED = True
    _two_providers_and_evals()
    from apps.profiles.models import TradingProfile
    from apps.threads.models import Thread

    prof = TradingProfile.objects.create(
        name="p", style="x", default_provider="claude", default_model="model-a"
    )
    thread = Thread.objects.create(kind="chat", profile=prof)
    # Pin is "model-a" even though "model-b" is better-measured.
    assert resolve_provider_and_model(thread=thread) == ("claude", "model-a")


@pytest.mark.django_db
def test_thin_eval_falls_through_to_first_enabled(settings):
    settings.AI_CALIBRATION_ROUTING_ENABLED = True
    settings.AI_CALIBRATION_ROUTING_MIN_SCORED = 5
    from apps.aieval.models import EvalRun
    from apps.secrets.models import ProviderConfig

    ProviderConfig.objects.create(provider="claude", enabled=True, default_model="model-a")
    ProviderConfig.objects.create(provider="openai", enabled=True, default_model="model-b")
    EvalRun.objects.create(model="model-b", scored=2, hit_rate=0.9)  # below MIN_SCORED floor
    assert resolve_provider_and_model(thread=_unpinned_thread()) == ("claude", "model-a")
