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
    ("retention_regime_days", "AI_RETENTION_REGIME_DAYS", 180),
    ("retention_desk_days", "AI_RETENTION_DESK_DAYS", 180),
    ("retention_book_days", "AI_RETENTION_BOOK_DAYS", 365),
    ("ai_failover_enabled", "AI_FAILOVER_ENABLED", True),
    ("ai_failover_provider", "AI_FAILOVER_PROVIDER", ""),
    ("observer_response_cache_enabled", "OBSERVER_RESPONSE_CACHE_ENABLED", True),
    ("observer_response_cache_ttl_seconds", "OBSERVER_RESPONSE_CACHE_TTL_SECONDS", 1800),
    ("aieval_scheduled_enabled", "AIEVAL_SCHEDULED_ENABLED", True),
    ("aieval_scheduled_model", "AIEVAL_SCHEDULED_MODEL", "claude-sonnet-4-6"),
    ("aieval_scheduled_horizon", "AIEVAL_SCHEDULED_HORIZON", 30),
    ("aieval_scheduled_limit", "AIEVAL_SCHEDULED_LIMIT", 25),
    ("tradingview_tools_enabled", "TRADINGVIEW_TOOLS_ENABLED", True),
    ("ai_calibration_routing_enabled", "AI_CALIBRATION_ROUTING_ENABLED", True),
    ("calibration_drift_sentinel_enabled", "CALIBRATION_DRIFT_SENTINEL_ENABLED", True),
    ("anomaly_sweep_enabled", "ANOMALY_SWEEP_ENABLED", True),
    ("returns_adjust_dividends", "RETURNS_ADJUST_DIVIDENDS", False),
    ("ai_investigation_max_iterations", "AI_INVESTIGATION_MAX_ITERATIONS", 8),
    # float literal, not 5: EDITABLE_FIELDS derives the coercer from type(default),
    # so an int here would make the API reject/ truncate a fractional dollar cap.
    ("ai_autonomous_daily_cap_usd", "AI_AUTONOMOUS_DAILY_CAP_USD", 5.0),
    ("ai_calibration_routing_min_scored", "AI_CALIBRATION_ROUTING_MIN_SCORED", 5),
    ("ai_calibration_routing_max_age_days", "AI_CALIBRATION_ROUTING_MAX_AGE_DAYS", 30),
    ("restore_from_ui_enabled", "RESTORE_FROM_UI_ENABLED", True),
    ("ai_chat_max_tool_iterations", "AI_CHAT_MAX_TOOL_ITERATIONS", 12),
    ("regime_narrative_enabled", "REGIME_NARRATIVE_ENABLED", True),
    ("book_narrative_enabled", "BOOK_NARRATIVE_ENABLED", True),
]

# Fields the API/UI may write, with a coercer per field — derived from _SPEC so the editable
# set and its types stay in lockstep with the resolved fields (one source of truth). The
# coercer is the Python type of the default (False→bool, 400→int, ""→str).
EDITABLE_FIELDS: dict[str, type] = {field: type(default) for field, _, default in _SPEC}


# One annotation per _SPEC row, same names: runtime_config() constructs this with
# **resolved, so a missing annotation raises TypeError on EVERY call, everywhere.
# apps/core/tests/test_system_settings.py pins the two sides equal.
@dataclass(frozen=True)
class RuntimeConfig:
    retention_ohlc_days: int
    retention_chain_days: int
    retention_notification_days: int
    retention_error_days: int
    retention_regime_days: int
    retention_desk_days: int
    retention_book_days: int
    ai_failover_enabled: bool
    ai_failover_provider: str
    observer_response_cache_enabled: bool
    observer_response_cache_ttl_seconds: int
    aieval_scheduled_enabled: bool
    aieval_scheduled_model: str
    aieval_scheduled_horizon: int
    aieval_scheduled_limit: int
    tradingview_tools_enabled: bool
    ai_calibration_routing_enabled: bool
    calibration_drift_sentinel_enabled: bool
    anomaly_sweep_enabled: bool
    returns_adjust_dividends: bool
    ai_investigation_max_iterations: int
    ai_autonomous_daily_cap_usd: float
    ai_calibration_routing_min_scored: int
    ai_calibration_routing_max_age_days: int
    restore_from_ui_enabled: bool
    ai_chat_max_tool_iterations: int
    regime_narrative_enabled: bool
    book_narrative_enabled: bool


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
