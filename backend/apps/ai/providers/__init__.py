"""Provider factory — resolves provider name to an instance.

Callers never `from apps.ai.providers.claude import ClaudeProvider` directly
in the task code; they go through `get_provider(...)`.
"""
from __future__ import annotations

from apps.ai.providers.base import Provider
from apps.ai.providers.claude import ClaudeProvider
from apps.ai.providers.local import LocalProvider
from apps.ai.providers.openai import OpenAIProvider


def get_provider(name: str, *, api_key: str, base_url: str = "") -> Provider:
    if name == "claude":
        return ClaudeProvider(api_key=api_key, base_url=base_url)
    if name == "openai":
        return OpenAIProvider(api_key=api_key, base_url=base_url)
    if name == "local":
        return LocalProvider(api_key=api_key, base_url=base_url)
    raise ValueError(f"Unknown provider: {name}")


__all__ = ["ClaudeProvider", "LocalProvider", "OpenAIProvider", "Provider", "get_provider"]
