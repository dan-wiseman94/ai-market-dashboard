"""Schwab OAuth2 helpers: build authorize URL, exchange code, refresh token, persist.

schwab-py handles refresh automatically for runtime clients via
`client_from_access_functions`, but we still need these for:
- Building the authorize URL shown in the frontend.
- Handling our web callback (schwab-py's built-in flows are CLI-oriented).
- Scheduled proactive refresh via Celery.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from secrets import token_urlsafe
from urllib.parse import urlencode

import httpx
import redis
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

log = logging.getLogger(__name__)

# OAuth `state` CSRF nonce (RFC 6749 §10.12). The callback is a cross-site-triggerable
# GET with no auth cookies, so CSRF middleware / SameSite don't cover it. We mint a
# one-time nonce in authorize and require it in the callback. Each minted nonce is stored
# under its OWN key (``schwab:oauth:state:<nonce>``) in the shared Redis — authorize and
# callback need not be the same web process, and Django's default cache is per-process
# LocMemCache. A short TTL bounds the consent round-trip. Per-nonce keys (rather than one
# shared key) let several "Connect" clicks have independent outstanding flows: completing
# an earlier one stays valid instead of being clobbered by a later mint (a clobbered state
# surfaces as a spurious 400 invalid_state and the new token never persists).
_OAUTH_STATE_KEY_PREFIX = "schwab:oauth:state:"
_OAUTH_STATE_TTL_SECONDS = 600  # 10 min: ample for user consent, short enough to bound replay


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _oauth_state_key(state: str) -> str:
    return f"{_OAUTH_STATE_KEY_PREFIX}{state}"


def new_oauth_state() -> str:
    """Mint + store a one-time OAuth `state` nonce, returning it for the authorize URL."""
    state = token_urlsafe(32)
    try:
        _redis().set(_oauth_state_key(state), "1", ex=_OAUTH_STATE_TTL_SECONDS)
    except Exception:  # best-effort store; a miss just makes the callback fail closed
        log.warning("Could not store Schwab OAuth state nonce", exc_info=True)
    return state


def consume_oauth_state(state: str | None) -> bool:
    """Return True iff ``state`` names a live nonce, deleting it (one-time use).

    Validate-and-delete is atomic: Redis ``DEL`` returns the number of keys removed, so a
    concurrent replay of the same nonce can win at most once. Fails closed (returns False)
    on a missing/unknown/empty nonce or any Redis hiccup, so a cross-site callback carrying
    an attacker's auth code is rejected before token exchange.
    """
    if not state:
        return False
    try:
        return _redis().delete(_oauth_state_key(state)) == 1
    except Exception:
        log.warning("Could not validate Schwab OAuth state nonce", exc_info=True)
        return False


class SchwabNotConfigured(RuntimeError):
    """Schwab OAuth was attempted without a client_id configured.

    Building an authorize URL with an empty client_id produces a request Schwab rejects
    with 401 invalid_client. Callers should surface this as a clear "set your credentials"
    message instead of bouncing the user to that opaque error.
    """


def schwab_app_credentials() -> tuple[str, str]:
    """Return (client_id, client_secret) for the registered Schwab app.

    DB-first (set via Settings → Connections), falling back to the SCHWAB_CLIENT_ID /
    SCHWAB_CLIENT_SECRET env settings (env-based and CI setups configure creds there).
    A blank DB value falls through to env per-field. Undecryptable DB creds (key rotated)
    degrade to the env values rather than raising.
    """
    from apps.secrets.models import SchwabAppConfig

    try:
        cfg = SchwabAppConfig.load()
        client_id = cfg.client_id or settings.SCHWAB_CLIENT_ID
        client_secret = cfg.client_secret or settings.SCHWAB_CLIENT_SECRET
    except InvalidToken:
        log.warning("Schwab app credentials undecryptable; falling back to env settings.")
        return settings.SCHWAB_CLIENT_ID, settings.SCHWAB_CLIENT_SECRET
    return client_id, client_secret


def build_authorize_url(*, state: str = "") -> str:
    from apps.core.mocks import is_mock_mode, run_service_scenario

    if is_mock_mode():
        # schwab-oauth-ok → canned authorize URL pointing at our own callback stub;
        # any other scenario falls back to the same deterministic stub.
        flow = run_service_scenario("schwab")
        if isinstance(flow, dict) and flow.get("authorize_url"):
            return flow["authorize_url"]
        return f"{settings.SCHWAB_CALLBACK_URL}?code=MOCK_OAUTH"

    client_id, _ = schwab_app_credentials()
    if not client_id:
        raise SchwabNotConfigured(
            "Schwab is not configured. Add your Schwab API credentials in "
            "Settings → Connections (or set SCHWAB_CLIENT_ID / SCHWAB_CLIENT_SECRET in .env)."
        )

    params = {
        "client_id": client_id,
        "redirect_uri": settings.SCHWAB_CALLBACK_URL,
        "response_type": "code",
    }
    if state:
        params["state"] = state
    return f"{settings.SCHWAB_AUTHORIZE_URL}?{urlencode(params)}"


def _post_token(data: dict) -> dict:
    """POST to Schwab's token endpoint and stamp the absolute expiry."""
    client_id, client_secret = schwab_app_credentials()
    resp = httpx.post(
        settings.SCHWAB_TOKEN_URL,
        data=data,
        auth=(client_id, client_secret),
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
    try:
        ApiCredential.objects.update_or_create(
            provider="schwab",
            defaults={"token": token, "expires_at": expires_at},
        )
    except InvalidToken:
        # The existing row's token is undecryptable (key rotated / salt reset), so
        # update_or_create's lookup SELECT can't read it via from_db_value — which would
        # crash the OAuth callback right when the user is trying to reconnect. Overwrite
        # with a fast delete (which doesn't decrypt) + create, making reconnect self-healing.
        log.warning("Overwriting undecryptable Schwab credential on reconnect.")
        with transaction.atomic():
            ApiCredential.objects.filter(provider="schwab").delete()
            ApiCredential.objects.create(provider="schwab", token=token, expires_at=expires_at)

    # A freshly persisted, working token resolves any prior rejection — clear the
    # cross-process auth-error marker so the connection status recovers immediately
    # rather than waiting for the next market read or the marker TTL.
    from apps.core import provider_health

    provider_health.clear_auth_error("schwab")


def load_token() -> dict | None:
    """Return the current token dict, or None if not connected."""
    from apps.secrets.models import ApiCredential

    try:
        return ApiCredential.objects.get(provider="schwab").token
    except ApiCredential.DoesNotExist:
        return None
    except InvalidToken:
        # Token encrypted under a now-gone key (DJANGO_SECRET_KEY rotated / salt reset);
        # decryption fires in the .get() row fetch. Treat as not-connected so callers behave
        # as unauthenticated instead of crashing. Reconnecting Schwab overwrites the dead row.
        log.warning(
            "Schwab credential is undecryptable (encryption key rotated or salt reset); "
            "reconnect Schwab to overwrite it."
        )
        return None
