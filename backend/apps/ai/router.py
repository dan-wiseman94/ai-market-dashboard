"""Resolve (provider, model) for an AI run per spec §6.5 precedence:

1. Per-send override
2. Thread.default_provider / .default_model (not present until M5 — threads don't have these yet)
3. Profile.default_provider / .default_model
4. Calibration-weighted fallback (M14 F2/F6, opt-in) — best-measured enabled model
5. First enabled ProviderConfig (+ its default_model)
"""

from __future__ import annotations

from django.conf import settings

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
            # defer the encrypted key: resolution needs only provider/default_model, and
            # decrypting here would raise InvalidToken on a key/salt change (see
            # encrypted-cred undecryptable trap) and crash an otherwise-resolvable run.
            cfg = ProviderConfig.objects.filter(provider=p, enabled=True).defer("_api_key").first()
            if cfg and cfg.default_model:
                return p, cfg.default_model

    if getattr(settings, "AI_CALIBRATION_ROUTING_ENABLED", False):
        choice = _calibration_choice()
        if choice is not None:
            return choice

    cfg = ProviderConfig.objects.filter(enabled=True).defer("_api_key").order_by("id").first()
    if cfg and cfg.default_model:
        return cfg.provider, cfg.default_model

    raise ResolutionError("No provider configured. Visit /settings to add one.")


def _calibration_choice() -> tuple[str, str] | None:
    """Best-MEASURED (provider, model) among enabled providers, or None (M14 F6).

    Considers each enabled ProviderConfig's default_model, looks up its most
    recent EvalRun, and keeps those with >= MIN_SCORED decisive calls inside the
    recency window. Ranks by hit_rate desc, then calibration_error asc. Returns
    None when nothing qualifies, so the caller falls through to first-enabled.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.aieval.services import latest_eval_for_model

    min_scored = int(getattr(settings, "AI_CALIBRATION_ROUTING_MIN_SCORED", 5))
    max_age_days = int(getattr(settings, "AI_CALIBRATION_ROUTING_MAX_AGE_DAYS", 30))
    cutoff = timezone.now() - timedelta(days=max_age_days)

    candidates: list[tuple[str, str, float, float]] = []
    for cfg in ProviderConfig.objects.filter(enabled=True):
        if not cfg.default_model:
            continue
        run = latest_eval_for_model(cfg.default_model)
        if run is None or run.created_at < cutoff:
            continue
        if (run.scored or 0) < min_scored or run.hit_rate is None:
            continue
        # calibration_error None sorts worst (1.0) on the tie-break.
        cal_err = run.calibration_error if run.calibration_error is not None else 1.0
        candidates.append((cfg.provider, cfg.default_model, run.hit_rate, cal_err))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c[2], c[3]))
    best = candidates[0]
    return best[0], best[1]
