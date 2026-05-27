"""Scheduled Schwab token maintenance."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.market.models import MarketEvent
from apps.market.services import events as events_service
from apps.profiles.models import WatchlistSymbol
from apps.secrets.models import ApiCredential
from apps.secrets.schwab_oauth import persist_token, refresh_token


@shared_task(name="market.refresh_schwab_token")
def refresh_schwab_token() -> dict:
    """Proactively refresh the Schwab access token when <5 min remains.

    Fired every minute by Celery beat (see config/celery.py).
    """
    try:
        cred = ApiCredential.objects.get(provider="schwab")
    except ApiCredential.DoesNotExist:
        return {"ok": False, "reason": "not_connected"}

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
