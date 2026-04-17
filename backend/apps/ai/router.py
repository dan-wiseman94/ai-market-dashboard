"""Resolve (provider, model) for an AI run per spec §6.5 precedence:

1. Per-send override
2. Thread.default_provider / .default_model (not present until M5 — threads don't have these yet)
3. Profile.default_provider / .default_model
4. First enabled ProviderConfig (+ its default_model)
"""
from __future__ import annotations

from apps.secrets.models import ProviderConfig
from apps.threads.models import Message, Thread


class ResolutionError(RuntimeError):
    """No provider could be resolved — surface to the UI as a 400-level error."""


def resolve_provider_and_model(
    *,
    thread: Thread,
    message: Message | None = None,
    override: dict | None = None,
) -> tuple[str, str]:
    """Return (provider_name, model_id). Raises ResolutionError if nothing matches."""
    if override:
        p = override.get("provider")
        m = override.get("model")
        if p and m:
            return p, m

    if thread.profile:
        p = thread.profile.default_provider or None
        m = thread.profile.default_model or None
        if p and m:
            return p, m
        if p:
            cfg = ProviderConfig.objects.filter(provider=p, enabled=True).first()
            if cfg and cfg.default_model:
                return p, cfg.default_model

    cfg = ProviderConfig.objects.filter(enabled=True).order_by("id").first()
    if cfg and cfg.default_model:
        return cfg.provider, cfg.default_model

    raise ResolutionError("No provider configured. Visit /settings to add one.")
