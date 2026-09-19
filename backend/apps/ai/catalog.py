"""Model catalog with per-model pricing. Source of truth for cost estimation and
per-model snapshot payload budgets.

Prices are USD per 1M tokens as published on each vendor's model page. Update
when providers revise.
"""

from __future__ import annotations

from dataclasses import dataclass

# Provider names that resolve to Anthropic endpoints. Anthropic-only paths
# (Messages Batches) must check membership before wrapping an arbitrary
# ProviderConfig in an Anthropic client — sending another vendor's key to
# api.anthropic.com fails every call with an opaque 401.
CLAUDE_FAMILY_PROVIDERS = ("claude", "anthropic")

# Fallback model per provider for best-effort / structured paths when no per-send
# or profile/schedule override and no ProviderConfig.default_model is set.
# Single source of truth — bump here, not in each caller.
DEFAULT_CLAUDE_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"


def default_model_for(provider: str) -> str:
    """The catalog fallback model for ``provider``; ``""`` for ``local`` (its models
    are user-declared, never assumed) and for unknown providers."""
    if provider in CLAUDE_FAMILY_PROVIDERS:
        return DEFAULT_CLAUDE_MODEL
    if provider == "openai":
        return DEFAULT_OPENAI_MODEL
    return ""


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
    max_payload_tokens: int = 40_000


_CATALOG: list[ModelInfo] = [
    ModelInfo(
        provider="claude",
        id="claude-fable-5-1",
        name="Claude Fable 5.1",
        input_per_mtok=10.00,
        output_per_mtok=50.00,
        cached_per_mtok=0.25,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-opus-5",
        name="Claude Opus 5",
        input_per_mtok=5.00,
        output_per_mtok=25.00,
        cached_per_mtok=0.50,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-sonnet-5",
        name="Claude Sonnet 5",
        input_per_mtok=2.00,
        output_per_mtok=10.00,
        cached_per_mtok=0.20,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-opus-4-8",
        name="Claude Opus 4.8",
        input_per_mtok=5.00,
        output_per_mtok=25.00,
        cached_per_mtok=0.50,
        context_window=1_000_000,
        supports_vision=True,
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="claude",
        id="claude-sonnet-4-6",
        name="Claude Sonnet 4.6",
        input_per_mtok=3.00,
        output_per_mtok=15.00,
        cached_per_mtok=0.375,
        context_window=1_000_000,
        supports_vision=True,
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
        max_payload_tokens=150_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-6-astra",
        name="GPT-6 Astra",
        input_per_mtok=10.00,
        output_per_mtok=50.00,
        cached_per_mtok=1.00,
        context_window=1_050_000,
        supports_vision=True,
        max_payload_tokens=300_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5.6-sol",
        name="GPT-5.6 Sol",
        input_per_mtok=4.00,
        output_per_mtok=20.00,
        cached_per_mtok=0.40,
        context_window=1_050_000,
        supports_vision=True,
        max_payload_tokens=300_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5",
        name="GPT-5",
        input_per_mtok=1.25,
        output_per_mtok=10.00,
        cached_per_mtok=0.125,
        context_window=400_000,
        supports_vision=True,
        max_payload_tokens=300_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5-mini",
        name="GPT-5 Mini",
        input_per_mtok=0.25,
        output_per_mtok=2.00,
        cached_per_mtok=0.025,
        context_window=400_000,
        supports_vision=True,
        max_payload_tokens=200_000,
    ),
    ModelInfo(
        provider="openai",
        id="gpt-5-nano",
        name="GPT-5 Nano",
        input_per_mtok=0.05,
        output_per_mtok=0.40,
        cached_per_mtok=0.005,
        context_window=400_000,
        supports_vision=False,
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
