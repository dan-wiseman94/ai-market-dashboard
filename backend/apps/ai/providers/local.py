"""Local provider — OpenAI-compatible endpoint (Ollama / LM Studio / vLLM / …).

Mechanically identical to OpenAIProvider; only name + base_url validation differ.
"""
from __future__ import annotations

from apps.ai.providers.openai import OpenAIProvider


class LocalProvider(OpenAIProvider):
    name = "local"

    def __init__(self, api_key: str, base_url: str) -> None:
        if not base_url:
            raise ValueError("LocalProvider requires a base_url (e.g. http://host.docker.internal:11434/v1).")
        super().__init__(api_key=api_key or "sk-local-placeholder", base_url=base_url)
