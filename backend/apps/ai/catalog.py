"""Model catalog with per-model pricing. Source of truth for cost estimation.

Pricing as of 2026-04. Update when providers revise.
"""
from __future__ import annotations

from dataclasses import dataclass


KNOWN_PROVIDERS = ["claude", "openai", "local"]


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


_CATALOG: list[ModelInfo] = [
    ModelInfo(
        provider="claude", id="claude-opus-4-7", name="Claude Opus 4.7",
        input_per_mtok=15.00, output_per_mtok=75.00, cached_per_mtok=1.875,
        context_window=200_000, supports_vision=True, supports_cache=True,
    ),
    ModelInfo(
        provider="claude", id="claude-sonnet-4-6", name="Claude Sonnet 4.6",
        input_per_mtok=3.00, output_per_mtok=15.00, cached_per_mtok=0.375,
        context_window=200_000, supports_vision=True, supports_cache=True,
    ),
    ModelInfo(
        provider="claude", id="claude-haiku-4-5-20251001", name="Claude Haiku 4.5",
        input_per_mtok=1.00, output_per_mtok=5.00, cached_per_mtok=0.125,
        context_window=200_000, supports_vision=True, supports_cache=True,
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
    entries = [m for m in _CATALOG if m.provider == provider]
    if not entries:
        return None
    return max(entries, key=lambda m: m.output_per_mtok)
