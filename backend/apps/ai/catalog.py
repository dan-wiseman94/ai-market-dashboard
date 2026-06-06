"""Model catalog with per-model pricing. Source of truth for cost estimation.

Pricing as of 2026-04. Update when providers revise.
"""

from __future__ import annotations

from dataclasses import dataclass

KNOWN_PROVIDERS = ["claude", "openai", "local"]

# The default Claude model for best-effort / structured paths when no per-send or
# profile/schedule override and no ProviderConfig.default_model is set. Single
# source of truth — bump here, not in each caller (was duplicated across ~8 sites).
DEFAULT_CLAUDE_MODEL = "claude-opus-4-8"


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    id: str
    name: str
    input_per_mtok: float
    output_per_mtok: float
    cached_per_mtok: float
    context_window: int
    supports_vision: bool
    supports_cache: bool
    max_payload_tokens: int = 40_000


_CATALOG: list[ModelInfo] = [
    ModelInfo(
        provider="claude",
        id="claude-opus-4-8",
        name="Claude Opus 4.8",
        input_per_mtok=15.00,
        output_per_mtok=75.00,
        cached_per_mtok=1.875,
        context_window=200_000,
        supports_vision=True,
        supports_cache=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-sonnet-4-6",
        name="Claude Sonnet 4.6",
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        cached_per_mtok=0.375,
        context_window=200_000,
        supports_vision=True,
        supports_cache=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-haiku-4-5-20251001",
        name="Claude Haiku 4.5",
        input_per_mtok=1.00,
        output_per_mtok=5.00,
        cached_per_mtok=0.125,
        context_window=200_000,
        supports_vision=True,
        supports_cache=True,
        max_payload_tokens=150_000,
    ),
    # OpenAI
    ModelInfo(
        provider="openai",
        id="gpt-5",
        name="GPT-5",
        input_per_mtok=5.00,
        output_per_mtok=40.00,
        cached_per_mtok=0.50,
        context_window=400_000,
        supports_vision=True,
        supports_cache=True,
        max_payload_tokens=300_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5-mini",
        name="GPT-5 Mini",
        input_per_mtok=0.60,
        output_per_mtok=4.80,
        cached_per_mtok=0.06,
        context_window=400_000,
        supports_vision=True,
        supports_cache=True,
        max_payload_tokens=200_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5-nano",
        name="GPT-5 Nano",
        input_per_mtok=0.15,
        output_per_mtok=1.20,
        cached_per_mtok=0.015,
        context_window=400_000,
        supports_vision=False,
        supports_cache=True,
        max_payload_tokens=200_000,
    ),
]


def list_models(provider: str | None = None) -> list[ModelInfo]:
    if provider is None:
        return list(_CATALOG)
    return [m for m in _CATALOG if m.provider == provider]


def get_model(provider: str, model_id: str) -> ModelInfo | None:
    for m in _CATALOG:
        if m.provider == provider and m.id == model_id:
            return m
    return None


def ceiling_for_provider(provider: str) -> ModelInfo | None:
    entries = list_models(provider)
    if not entries:
        return None
    return max(entries, key=lambda m: m.output_per_mtok)
