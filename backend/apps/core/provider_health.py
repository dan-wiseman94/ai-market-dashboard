"""Cross-process provider auth-health markers.

When a market-data provider rejects a stored credential (e.g. Schwab returns
401/403 on a revoked OAuth token), the rejection usually happens in the *worker*
(snapshot capture / observer) while the connection-status UI is served by *web*.
Django's default cache is per-process ``LocMemCache``, so a marker set in one
process would be invisible to the other. We record it in the shared Redis (the
project's cross-process store, same as ``apps.market.cache``) keyed by provider,
with a TTL so it self-heals if the provider is never called again after a blip.

Reads degrade to "no known error" on any Redis hiccup — a status endpoint must
never 500 because of an auxiliary marker lookup.
"""

from __future__ import annotations

import logging

import redis
from django.conf import settings

log = logging.getLogger(__name__)

# How long an auth-error marker lives if nothing clears it. Bounds staleness when
# the provider is never called again after a rejection.
_TTL_SECONDS = 3600


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _key(provider: str) -> str:
    return f"provider_health:auth_error:{provider}"


def mark_auth_error(provider: str, message: str) -> None:
    """Record that ``provider`` rejected its stored credential."""
    try:
        _redis().set(_key(provider), message, ex=_TTL_SECONDS)
    except Exception:  # pragma: no cover - best-effort; a marker write must never raise
        log.warning("Could not record %s auth-error marker", provider, exc_info=True)


def clear_auth_error(provider: str) -> None:
    """Clear ``provider``'s auth-error marker (call after a successful request)."""
    try:
        _redis().delete(_key(provider))
    except Exception:  # pragma: no cover - best-effort
        log.warning("Could not clear %s auth-error marker", provider, exc_info=True)


def auth_error(provider: str) -> str | None:
    """Return the last recorded auth-error message for ``provider``, or None."""
    try:
        raw = _redis().get(_key(provider))
    except Exception:
        return None
    if raw is None:
        return None
    return raw.decode() if isinstance(raw, bytes) else str(raw)
