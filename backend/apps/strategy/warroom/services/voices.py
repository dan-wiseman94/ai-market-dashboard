"""Assign debate personas to providers per voice_mode. Multi-provider diversity
when >1 provider is enabled+configured, else everyone on the default."""

from __future__ import annotations

from apps.strategy.warroom import constants as C


def _enabled_providers() -> list[tuple[str, str]]:
    """[(provider, default_model), ...] for enabled providers that have a model."""
    from apps.secrets.models import ProviderConfig

    out = []
    for cfg in ProviderConfig.objects.filter(enabled=True):
        model = cfg.default_model or ""
        if model:
            out.append((cfg.provider, model))
    return out


def assign_voices(voice_mode: str) -> list[tuple[str, str, str]]:
    """Return [(persona, provider, model), ...] for bull/bear/skeptic."""
    providers = _enabled_providers()
    if not providers:
        return [(p, "", "") for p in C.PERSONAS]
    if voice_mode != "multi" or len(providers) == 1:
        prov, model = providers[0]
        return [(p, prov, model) for p in C.PERSONAS]
    out = []
    for i, persona in enumerate(C.PERSONAS):
        prov, model = providers[i % len(providers)]
        out.append((persona, prov, model))
    return out
