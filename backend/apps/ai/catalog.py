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

# How a model accepts extended thinking on the wire.
#   THINKING_ADAPTIVE — `thinking={"type": "adaptive", "display": ...}` plus
#     `output_config={"effort": ...}`; `budget_tokens` is rejected with a 400.
#   THINKING_BUDGET   — `thinking={"type": "enabled", "budget_tokens": N}` (N >= 1024
#     and strictly below max_tokens); adaptive and `effort` are both rejected.
#   THINKING_NONE     — the provider has no extended-thinking surface.
# Omitting `thinking` on an adaptive row does NOT disable it: those models think by
# default, so an off switch has to send `{"type": "disabled"}` explicitly — and that
# pairing is itself rejected above effort `high`, so the effort hint is dropped with it.
THINKING_ADAPTIVE = "adaptive"
THINKING_BUDGET = "budget"
THINKING_NONE = "none"

# The effort ladder, cheapest first. A model exposes a subset; `effort_levels=()`
# means the model rejects `output_config.effort` outright.
EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
# The API's own default when `effort` is omitted.
DEFAULT_EFFORT = "high"


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
    # Extended-thinking wire shape and the effort levels this row accepts. The
    # Claude provider branches on these; sending the wrong shape is a 400.
    thinking: str = THINKING_ADAPTIVE
    effort_levels: tuple[str, ...] = EFFORT_LEVELS
    # False where thinking is always on and `{"type": "disabled"}` is a 400. Turning
    # thinking off on such a row is not expressible, so the run still thinks.
    thinking_can_disable: bool = True


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
        # Thinking is always on here; {"type": "disabled"} is rejected.
        thinking_can_disable=False,
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
        # Takes adaptive thinking; the xhigh rung is not in its effort ladder.
        effort_levels=("low", "medium", "high", "max"),
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
        thinking=THINKING_BUDGET,
        effort_levels=(),
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
        thinking=THINKING_NONE,
        effort_levels=(),
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
        thinking=THINKING_NONE,
        effort_levels=(),
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
        thinking=THINKING_NONE,
        effort_levels=(),
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
        thinking=THINKING_NONE,
        effort_levels=(),
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
        thinking=THINKING_NONE,
        effort_levels=(),
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


def thinking_style(provider: str, model_id: str) -> str:
    """The extended-thinking wire shape ``model_id`` accepts.

    An id the catalog doesn't carry resolves to ``THINKING_ADAPTIVE``: the adaptive
    shape is what every current Claude row takes, so it is the safe read for an id
    added upstream before the catalog caught up. Add the row here to override.
    """
    info = get_model(provider, model_id)
    return info.thinking if info else THINKING_ADAPTIVE


def resolve_effort(provider: str, model_id: str, effort: str) -> str:
    """Clamp ``effort`` to a level ``model_id`` accepts; ``""`` to omit the param.

    A level the model doesn't expose steps DOWN the ladder (``xhigh`` on a row that
    stops at ``high``) — stepping up would spend more than the caller asked for.
    An unrecognized string falls back to the API's own default.
    """
    if not effort:
        return ""
    info = get_model(provider, model_id)
    levels = info.effort_levels if info else EFFORT_LEVELS
    if not levels:
        return ""
    if effort in levels:
        return effort
    if effort not in EFFORT_LEVELS:
        return DEFAULT_EFFORT if DEFAULT_EFFORT in levels else levels[-1]
    for candidate in reversed(EFFORT_LEVELS[: EFFORT_LEVELS.index(effort)]):
        if candidate in levels:
            return candidate
    return levels[0]


def ceiling_for_provider(provider: str) -> ModelInfo | None:
    entries = list_models(provider)
    if not entries:
        return None
    return max(entries, key=lambda m: m.output_per_mtok)


def catalog_owner(model_id: str) -> str | None:
    """The provider whose catalog row has ``model_id``; None for ids the catalog does not know."""
    for m in _CATALOG:
        if m.id == model_id:
            return m.provider
    return None


def is_foreign_model(provider: str, model: str) -> bool:
    """True when ``model`` is a catalog row for a provider other than ``provider``.

    An id unknown to the catalog (a local model name, a brand-new vendor id) is not
    foreign — it is accepted verbatim. Any name in ``CLAUDE_FAMILY_PROVIDERS`` owns
    the ``claude`` rows.
    """
    if not model:
        return False
    owner = catalog_owner(model)
    if owner is None:
        return False
    family = "claude" if provider in CLAUDE_FAMILY_PROVIDERS else provider
    return owner != family


def foreign_model_error(provider: str, model: str) -> str | None:
    """A field-error message when ``model`` belongs to another provider's catalog, else None."""
    if not is_foreign_model(provider, model):
        return None
    owner = catalog_owner(model)
    article = "an" if owner and owner[0] in "aeiou" else "a"
    return (
        f"{model} is {article} {owner} catalog model; pick a {provider} model or clear the field."
    )
