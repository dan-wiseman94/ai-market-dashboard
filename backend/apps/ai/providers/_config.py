"""Shared client-construction helpers for AI provider resilience."""

from __future__ import annotations


def client_kwargs() -> dict:
    """Resilience kwargs for the Anthropic/OpenAI SDK clients: bounded retry + timeout.

    Both SDKs accept max_retries (exponential backoff on 408/409/429/5xx) and timeout.
    Read from Django settings (env-configurable). NOT routed through SystemSettings/DB: this
    runs at provider __init__, which can happen inside the async streaming loop, where a sync
    ORM read would raise SynchronousOnlyOperation. Keep it env-only.
    """
    from django.conf import settings

    return {
        "max_retries": getattr(settings, "AI_PROVIDER_MAX_RETRIES", 2),
        "timeout": getattr(settings, "AI_PROVIDER_TIMEOUT_SECONDS", 60.0),
    }
