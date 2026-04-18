"""Schwab OAuth2 helpers: build authorize URL, exchange code, refresh token, persist.

schwab-py handles refresh automatically for runtime clients via
`client_from_access_functions`, but we still need these for:
- Building the authorize URL shown in the frontend.
- Handling our web callback (schwab-py's built-in flows are CLI-oriented).
- Scheduled proactive refresh via Celery.
"""
from __future__ import annotations

import time
from datetime import datetime
from urllib.parse import urlencode

import httpx
from django.conf import settings
from django.utils import timezone


def build_authorize_url(*, state: str = "") -> str:
    params = {
        "client_id": settings.SCHWAB_CLIENT_ID,
        "redirect_uri": settings.SCHWAB_CALLBACK_URL,
        "response_type": "code",
    }
    if state:
        params["state"] = state
    return f"{settings.SCHWAB_AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    """Exchange an authorization code for an access/refresh token."""
    resp = httpx.post(
        settings.SCHWAB_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.SCHWAB_CALLBACK_URL,
        },
        auth=(settings.SCHWAB_CLIENT_ID, settings.SCHWAB_CLIENT_SECRET),
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    body["expires_at"] = int(time.time()) + int(body.get("expires_in", 1800))
    return body


def refresh_token(refresh_token_value: str) -> dict:
    """Use a refresh token to obtain a new access token."""
    resp = httpx.post(
        settings.SCHWAB_TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token_value},
        auth=(settings.SCHWAB_CLIENT_ID, settings.SCHWAB_CLIENT_SECRET),
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    body["expires_at"] = int(time.time()) + int(body.get("expires_in", 1800))
    return body


def persist_token(token: dict) -> None:
    """Upsert the schwab token into ApiCredential."""
    from apps.secrets.models import ApiCredential

    expires_at = datetime.fromtimestamp(token["expires_at"], tz=timezone.get_current_timezone())
    ApiCredential.objects.update_or_create(
        provider="schwab",
        defaults={"token": token, "expires_at": expires_at},
    )


def load_token() -> dict | None:
    """Return the current token dict, or None if not connected."""
    from apps.secrets.models import ApiCredential

    try:
        return ApiCredential.objects.get(provider="schwab").token
    except ApiCredential.DoesNotExist:
        return None
