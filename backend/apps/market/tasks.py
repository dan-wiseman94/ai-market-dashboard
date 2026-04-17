"""Scheduled Schwab token maintenance."""
from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.secrets.models import ApiCredential
from apps.secrets.schwab_oauth import refresh_token, persist_token


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
