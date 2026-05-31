"""Scheduled Schwab token maintenance."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from cryptography.fernet import InvalidToken
from django.utils import timezone

from apps.market.models import MarketEvent
from apps.market.services import events as events_service
from apps.profiles.models import WatchlistSymbol
from apps.secrets.models import ApiCredential
from apps.secrets.schwab_oauth import persist_token, refresh_token

log = logging.getLogger(__name__)


@shared_task(name="market.refresh_schwab_token")
def refresh_schwab_token() -> dict:
    """Proactively refresh the Schwab access token when <5 min remains.

    Fired every minute by Celery beat (see config/celery.py).
    """
    try:
        cred = ApiCredential.objects.get(provider="schwab")
    except ApiCredential.DoesNotExist:
        return {"ok": False, "reason": "not_connected"}
    except InvalidToken:
        # The stored token was encrypted under a key that no longer exists (DJANGO_SECRET_KEY
        # rotated or /data salt reset). It is unrecoverable — decryption fires during the .get()
        # row fetch via EncryptedJSONField.from_db_value. Degrade to a no-op instead of raising
        # an unhandled traceback every beat tick; reconnecting Schwab overwrites the row.
        log.warning(
            "Schwab credential is undecryptable (encryption key rotated or salt reset); "
            "reconnect Schwab to overwrite it."
        )
        return {"ok": False, "reason": "undecryptable"}

    if cred.expires_at and cred.expires_at > timezone.now() + timedelta(minutes=5):
        return {"ok": False, "reason": "fresh"}

    refresh_value = cred.token.get("refresh_token") if cred.token else None
    if not refresh_value:
        return {"ok": False, "reason": "no_refresh_token"}

    new_token = refresh_token(refresh_value)
    persist_token(new_token)
    return {"ok": True}


@shared_task(name="market.refresh_events")
def refresh_events() -> dict:
    """Daily refresh of the MarketEvent store for all watchlist tickers + curated macro."""
    tickers = list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())
    n_earn = len(events_service.fetch_earnings(tickers))
    n_macro = len(events_service.fetch_macro())
    cutoff = timezone.now() - timedelta(days=30)
    pruned, _ = MarketEvent.objects.filter(event_time__lt=cutoff).delete()
    return {"earnings": n_earn, "macro": n_macro, "pruned": pruned}


@shared_task(name="market.ingest_daily_bars")
def ingest_daily_bars() -> dict:
    """Fetch + persist daily OHLCBar for a fixed universe (watchlist + sector ETFs +
    $SPX/QQQ + macro proxies). Idempotent via fetch_ohlc's update_or_create. Densifies
    the bar history that relative-strength, sector-rotation, the backtester, the leaderboard,
    and unusual-options IV-z all read. Never raises -- a per-symbol failure is logged and skipped."""
    from apps.market.services.context import MACRO, SECTOR_ETFS
    from apps.market.services.ohlc import fetch_ohlc
    from apps.profiles.models import WatchlistSymbol

    watchlist = list(WatchlistSymbol.objects.values_list("ticker", flat=True).distinct())
    universe = sorted(
        {s.upper() for s in [*watchlist, "$SPX", "QQQ", *SECTOR_ETFS, *MACRO.values()] if s}
    )
    ingested = 0
    for sym in universe:
        try:
            fetch_ohlc(sym, timeframe="1d", bars=60)
            ingested += 1
        except Exception as exc:
            log.warning("market.ingest_daily_bars %s failed: %s", sym, exc)
    return {"requested": len(universe), "ingested": ingested}
