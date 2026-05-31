"""Resolve runtime-tunable knobs: DB override (SystemSettings) first, else the Django
setting / env default.

This is the single place that merges UI-set values with the env-based defaults. Callers
get a frozen snapshot via ``runtime_config()`` and read attributes; one row fetch per call.
A NULL field on the singleton means "inherit", so unset values (and test
``override_settings``) fall through to the corresponding setting.
"""

from __future__ import annotations

from dataclasses import dataclass

# (dataclass field, Django settings name, hard default) — the hard default mirrors the
# settings.py default and is only used if the setting itself is somehow absent.
_SPEC: list[tuple[str, str, object]] = [
    ("retention_ohlc_days", "AI_RETENTION_OHLC_DAYS", 400),
    ("retention_chain_days", "AI_RETENTION_CHAIN_DAYS", 120),
    ("retention_notification_days", "AI_RETENTION_NOTIFICATION_DAYS", 90),
    ("retention_error_days", "AI_RETENTION_ERROR_DAYS", 90),
    ("ai_failover_enabled", "AI_FAILOVER_ENABLED", False),
    ("ai_failover_provider", "AI_FAILOVER_PROVIDER", ""),
    ("observer_response_cache_enabled", "OBSERVER_RESPONSE_CACHE_ENABLED", False),
    ("observer_response_cache_ttl_seconds", "OBSERVER_RESPONSE_CACHE_TTL_SECONDS", 1800),
    ("aieval_scheduled_enabled", "AIEVAL_SCHEDULED_ENABLED", False),
    ("aieval_scheduled_model", "AIEVAL_SCHEDULED_MODEL", "claude-sonnet-4-6"),
    ("aieval_scheduled_horizon", "AIEVAL_SCHEDULED_HORIZON", 30),
    ("aieval_scheduled_limit", "AIEVAL_SCHEDULED_LIMIT", 25),
]

# Fields the API/UI may write, with a coercer for incoming JSON values.
EDITABLE_FIELDS: dict[str, type] = {
    "retention_ohlc_days": int,
    "retention_chain_days": int,
    "retention_notification_days": int,
    "retention_error_days": int,
    "ai_failover_enabled": bool,
    "ai_failover_provider": str,
    "observer_response_cache_enabled": bool,
    "observer_response_cache_ttl_seconds": int,
    "aieval_scheduled_enabled": bool,
    "aieval_scheduled_model": str,
    "aieval_scheduled_horizon": int,
    "aieval_scheduled_limit": int,
}


@dataclass(frozen=True)
class RuntimeConfig:
    retention_ohlc_days: int
    retention_chain_days: int
    retention_notification_days: int
    retention_error_days: int
    ai_failover_enabled: bool
    ai_failover_provider: str
    observer_response_cache_enabled: bool
    observer_response_cache_ttl_seconds: int
    aieval_scheduled_enabled: bool
    aieval_scheduled_model: str
    aieval_scheduled_horizon: int
    aieval_scheduled_limit: int


def runtime_config() -> RuntimeConfig:
    """Resolved snapshot: SystemSettings override where non-NULL, else the Django setting."""
    from django.conf import settings

    from apps.core.models import SystemSettings

    cfg = SystemSettings.load()
    resolved: dict[str, object] = {}
    for field, setting_name, default in _SPEC:
        value = getattr(cfg, field)
        resolved[field] = value if value is not None else getattr(settings, setting_name, default)
    return RuntimeConfig(**resolved)  # type: ignore[arg-type]
