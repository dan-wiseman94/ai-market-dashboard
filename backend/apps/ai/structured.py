"""Provider-neutral one-shot structured output.

The public entry point for every caller that needs a typed Pydantic result in
one call (observer structured mode and consensus, the eval harness, post-mortems,
coverage revisions, regime/book narratives, the War Room verdict). Dispatches
to the Anthropic ``messages.parse`` implementation for Claude-family providers
and to the OpenAI-compatible implementation for ``openai`` and ``local``. Both
record an ``AIRun`` under the real provider so cost caps see the spend.

Target resolution follows the same precedence as ``apps.ai.router`` (explicit
override, then the profile's defaults, then calibration-weighted routing
(opt-in), then the first enabled ``ProviderConfig``) except that an override or
profile that names a provider does not fall through to the global tiers when
that provider is unusable. A target is usable when its config is enabled and
carries a credential — a key for ``claude``/``openai``, a base URL for
``local``. A requested model that is a catalog row of a *different* provider is
ignored (falling back to the config's own default) rather than sent to a
provider it doesn't belong to.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, NamedTuple

from cryptography.fernet import InvalidToken
from django.conf import settings
from pydantic import BaseModel

from apps.ai.catalog import CLAUDE_FAMILY_PROVIDERS, default_model_for, is_foreign_model
from apps.ai.providers import claude_structured, openai_structured
from apps.ai.providers.claude_structured import StructuredParseError, token_usage_from_anthropic
from apps.ai.providers.openai_structured import token_usage_from_openai

if TYPE_CHECKING:
    from apps.profiles.models import TradingProfile

log = logging.getLogger(__name__)

OPENAI_COMPATIBLE_PROVIDERS = ("openai", "local")

__all__ = [
    "OPENAI_COMPATIBLE_PROVIDERS",
    "StructuredParseError",
    "StructuredTarget",
    "ensure_within_caps",
    "resolve_structured_target",
    "run_structured",
    "structured_capable_targets",
    "token_usage_from_anthropic",
    "token_usage_from_openai",
]


def run_structured[M: BaseModel](
    *,
    provider: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    output_model: type[M],
    max_tokens: int = 2048,
    base_url: str = "",
) -> M:
    """Run ``output_model`` as a one-shot structured call on ``provider``."""
    if provider in CLAUDE_FAMILY_PROVIDERS:
        return claude_structured.run_structured(
            api_key=api_key,
            model=model,
            system=system,
            user=user,
            output_model=output_model,
            max_tokens=max_tokens,
            base_url=base_url,
        )
    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        return openai_structured.run_structured(
            provider=provider,
            api_key=api_key,
            model=model,
            system=system,
            user=user,
            output_model=output_model,
            max_tokens=max_tokens,
            base_url=base_url,
        )
    raise ValueError(f"Unknown provider for structured output: {provider!r}")


class StructuredTarget(NamedTuple):
    """A usable (provider, model) plus the credential and caps a caller needs.

    Named fields keep the secret ``api_key`` distinct from the loggable
    ``provider``/``model`` for data-flow analysis; it still unpacks like a tuple.
    """

    provider: str
    model: str
    api_key: str
    base_url: str
    daily_cap: Decimal
    monthly_cap: Decimal | None


def _target_from_config(cfg, *, model: str = "") -> StructuredTarget | None:
    """Build a target from ``cfg`` or return None when it is missing, disabled, or
    lacks a credential/model. Reads the encrypted key, so ``InvalidToken`` can raise.

    A ``model`` that names a catalog row of a different provider (e.g. a profile's
    Claude-family default surviving a switch to ``openai``) is ignored — never sent
    to a provider it doesn't belong to — and resolution falls back to the config's
    own default model.
    """
    if cfg is None or not cfg.enabled:
        return None
    key = cfg.api_key
    base_url = cfg.base_url or ""
    if cfg.provider == "local":
        if not base_url:
            return None
    elif not key:
        return None
    if is_foreign_model(cfg.provider, model):
        log.warning(
            "structured: model %r belongs to a different provider's catalog than %s; "
            "using the provider default instead",
            model,
            cfg.provider,
        )
        model = ""
    model_id = model or cfg.default_model or default_model_for(cfg.provider)
    if not model_id:
        return None
    return StructuredTarget(
        provider=cfg.provider,
        model=model_id,
        api_key=key,
        base_url=base_url,
        daily_cap=cfg.daily_cost_cap_usd,
        monthly_cap=cfg.monthly_cost_cap_usd,
    )


def resolve_structured_target(
    *,
    profile: TradingProfile | None = None,
    override_provider: str = "",
    override_model: str = "",
) -> StructuredTarget | None:
    """The target a structured caller should use, or None when nothing usable exists.

    Precedence: ``override_provider`` → ``profile.default_provider`` →
    calibration-weighted choice (``AI_CALIBRATION_ROUTING_ENABLED``) → first enabled
    config. An override or profile that names a provider does not fall through to
    the global tiers when that provider is unusable. ``InvalidToken`` propagates so
    callers can report an undecryptable key.
    """
    from apps.secrets.models import ProviderConfig

    if override_provider:
        cfg = ProviderConfig.objects.filter(provider=override_provider, enabled=True).first()
        return _target_from_config(cfg, model=override_model)
    if profile is not None and profile.default_provider:
        cfg = ProviderConfig.objects.filter(provider=profile.default_provider, enabled=True).first()
        return _target_from_config(cfg, model=profile.default_model or "")
    if getattr(settings, "AI_CALIBRATION_ROUTING_ENABLED", False):
        from apps.ai.router import _calibration_choice

        choice = _calibration_choice()
        if choice is not None:
            prov, model_id = choice
            cfg = ProviderConfig.objects.filter(provider=prov, enabled=True).first()
            target = _target_from_config(cfg, model=model_id)
            if target is not None:
                return target
    cfg = ProviderConfig.objects.filter(enabled=True).order_by("id").first()
    return _target_from_config(cfg)


def structured_capable_targets() -> list[StructuredTarget]:
    """Every enabled provider with a usable credential and a resolvable model, one
    per config, ordered by provider name. Undecryptable keys are skipped with a
    warning so a consensus fan-out never crashes on a key/salt rotation."""
    from apps.secrets.models import ProviderConfig

    targets: list[StructuredTarget] = []
    # defer the encrypted key: materializing a row decrypts it eagerly (from_db_value
    # runs during iteration), which would raise InvalidToken for the whole loop before
    # the per-row try/except below ever runs. Deferring pushes the decrypt to the
    # `cfg.api_key` read inside `_target_from_config`, so only that row is skipped.
    for cfg in ProviderConfig.objects.filter(enabled=True).order_by("provider").defer("_api_key"):
        try:
            target = _target_from_config(cfg)
        except InvalidToken:
            log.warning("structured: %s API key could not be decrypted; skipping", cfg.provider)
            continue
        if target is not None:
            targets.append(target)
    return targets


def ensure_within_caps(target: StructuredTarget) -> None:
    """Raise ``CostCapExceededError`` when ``target.provider`` is over its daily or
    monthly cap. Reads AIRun spend only; never calls the model."""
    from apps.ai.cost import check_daily_cap, check_monthly_cap

    check_daily_cap(target.provider, cap_usd=target.daily_cap)
    check_monthly_cap(target.provider, cap_usd=target.monthly_cap)
