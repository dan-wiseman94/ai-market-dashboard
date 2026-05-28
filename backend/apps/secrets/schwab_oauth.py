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
    from apps.core.mocks import is_mock_mode, run_service_scenario

    if is_mock_mode():
        # schwab-oauth-ok → canned authorize URL pointing at our own callback stub;
        # any other scenario falls back to the same deterministic stub.
        flow = run_service_scenario("schwab")
        if isinstance(flow, dict) and flow.get("authorize_url"):
            return flow["authorize_url"]
        return f"{settings.SCHWAB_CALLBACK_URL}?code=MOCK_OAUTH"

    params = {
        "client_id": settings.SCHWAB_CLIENT_ID,
        "redirect_uri": settings.SCHWAB_CALLBACK_URL,
        "response_type": "code",
    }
    if state:
        params["state"] = state
    return f"{settings.SCHWAB_AUTHORIZE_URL}?{urlencode(params)}"


def _post_token(data: dict) -> dict:
    """POST to Schwab's token endpoint and stamp the absolute expiry."""
    resp = httpx.post(
        settings.SCHWAB_TOKEN_URL,
        data=data,
        auth=(settings.SCHWAB_CLIENT_ID, settings.SCHWAB_CLIENT_SECRET),
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    body["expires_at"] = int(time.time()) + int(body.get("expires_in", 1800))
    return body


def exchange_code_for_token(code: str) -> dict:
    """Exchange an authorization code for an access/refresh token."""
    from apps.core.mocks import is_mock_mode, run_service_scenario

    if is_mock_mode():
        # Honor schwab-oauth-ok's canned tokens; map its {access,refresh} shape onto
        # the schwab-py token shape the persistence layer expects. No real HTTP.
        flow = run_service_scenario("schwab")
        raw = flow.get("tokens") if isinstance(flow, dict) else None
        token = {
            "access_token": (raw or {}).get("access", "mock-access"),
            "refresh_token": (raw or {}).get("refresh", "mock-refresh"),
            "expires_in": 1800,
        }
        token["expires_at"] = int(time.time()) + token["expires_in"]
        return token

    return _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.SCHWAB_CALLBACK_URL,
        }
    )


def refresh_token(refresh_token_value: str) -> dict:
    """Use a refresh token to obtain a new access token."""
    return _post_token({"grant_type": "refresh_token", "refresh_token": refresh_token_value})


def persist_token(token: dict) -> None:
    """Upsert the schwab token into ApiCredential."""
    from apps.secrets.models import ApiCredential

    # Record when the token was first created (schwab-py tracks refresh-token age
    # off this). Set once; refresh writes carry the original value through.
    token.setdefault("creation_timestamp", int(time.time()))
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
