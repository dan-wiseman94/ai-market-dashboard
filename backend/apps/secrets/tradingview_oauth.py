"""TradingView MCP OAuth 2.1 client: discovery, dynamic registration, PKCE authorize,
code exchange, refresh, persistence.

Mirrors ``schwab_oauth`` (per-nonce Redis state, InvalidToken self-heal on reconnect,
provider_health marker) but follows the MCP authorization spec: the authorization
server is discovered from the MCP server's protected-resource metadata (RFC 9728), the
client registers itself dynamically (RFC 7591, a fresh public client per Connect click),
and every authorize/token request carries the MCP server URL as ``resource`` (RFC 8707).
Refresh is lazy (``ensure_fresh_token``) under a Redis lock — there is no beat task.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from secrets import token_urlsafe
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import redis
from cryptography.fernet import InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.market.services.safe_log import scrub_secret_params

log = logging.getLogger(__name__)

SCOPE = "mcp:read mcp:tools"
CLIENT_NAME = "Ledger"
REJECTED_MESSAGE = "TradingView rejected the stored token; reconnect in Settings → Connections."
_TIMEOUT = 15.0

_STATE_KEY_PREFIX = "tradingview:oauth:state:"
_STATE_TTL_SECONDS = 600  # ample for consent, short enough to bound replay
_METADATA_KEY = "tradingview:oauth:metadata"
_METADATA_TTL_SECONDS = 86_400
_REFRESH_LOCK_KEY = "tradingview:oauth:refresh_lock"
_REFRESH_LOCK_TTL_SECONDS = 30
_REFRESH_SKEW_SECONDS = 60
_RESOURCE_METADATA_RE = re.compile(r'resource_metadata="([^"]+)"')


class TradingViewOAuthError(RuntimeError):
    """Discovery, registration, or token-endpoint failure. Message is client-safe."""


class TradingViewTokenRejected(TradingViewOAuthError):
    """The token endpoint rejected our grant (HTTP 400/401) — a reconnect is required."""


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def mcp_url() -> str:
    return str(settings.TRADINGVIEW_MCP_URL)


# --- discovery -------------------------------------------------------------------------


def _protected_resource_metadata_url(resource: str) -> str:
    """RFC 9728 path-based document: insert the well-known segment before the path."""
    parts = urlsplit(resource)
    path = parts.path.rstrip("/")
    return urlunsplit(
        (parts.scheme, parts.netloc, f"/.well-known/oauth-protected-resource{path}", "", "")
    )


def _get_json(url: str) -> dict | None:
    try:
        resp = httpx.get(url, headers={"Accept": "application/json"}, timeout=_TIMEOUT)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        body = resp.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _resource_metadata_url_from_challenge() -> str | None:
    """Fallback discovery: an unauthenticated ``initialize`` answers 401 with a
    ``WWW-Authenticate: Bearer resource_metadata="…"`` pointer."""
    try:
        resp = httpx.post(
            mcp_url(),
            json={"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}},
            headers={"Accept": "application/json, text/event-stream"},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError:
        return None
    match = _RESOURCE_METADATA_RE.search(resp.headers.get("WWW-Authenticate", ""))
    return match.group(1) if match else None


def discover() -> dict:
    """Authorization-server metadata (RFC 8414) for the MCP server, cached 24h in Redis.

    Raises TradingViewOAuthError when any hop fails or the document lacks the endpoints."""
    r = _redis()
    try:
        cached: bytes | None = r.get(_METADATA_KEY)  # type: ignore[assignment]
    except Exception:
        cached = None
    if cached:
        return json.loads(cached)

    prm = _get_json(_protected_resource_metadata_url(mcp_url()))
    if prm is None:
        pointer = _resource_metadata_url_from_challenge()
        prm = _get_json(pointer) if pointer else None
    servers = (prm or {}).get("authorization_servers") or []
    if not servers:
        raise TradingViewOAuthError("Could not discover TradingView's authorization server.")
    issuer = str(servers[0]).rstrip("/")
    meta = _get_json(f"{issuer}/.well-known/oauth-authorization-server")
    required = ("authorization_endpoint", "token_endpoint", "registration_endpoint")
    if meta is None or any(not meta.get(k) for k in required):
        raise TradingViewOAuthError("TradingView's authorization-server metadata is incomplete.")
    try:
        r.set(_METADATA_KEY, json.dumps(meta), ex=_METADATA_TTL_SECONDS)
    except Exception:
        log.warning("Could not cache TradingView OAuth metadata", exc_info=True)
    return meta


# --- registration + authorize ----------------------------------------------------------


def _failure_message(prefix: str, resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    detail = ""
    if isinstance(body, dict):
        detail = str(body.get("error_description") or body.get("error") or "")
    detail = scrub_secret_params(detail)[:200]
    return f"{prefix} (HTTP {resp.status_code})" + (f": {detail}" if detail else "")


def register_client(meta: dict) -> dict:
    """Dynamically register a public client (RFC 7591).

    Returns ``{"client_id": str, "client_secret": str}`` (secret "" for a public client)."""
    payload = {
        "client_name": CLIENT_NAME,
        "redirect_uris": [settings.TRADINGVIEW_CALLBACK_URL],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": SCOPE,
    }
    try:
        resp = httpx.post(meta["registration_endpoint"], json=payload, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise TradingViewOAuthError("Could not reach TradingView's registration endpoint.") from exc
    if resp.status_code not in (200, 201):
        raise TradingViewOAuthError(
            _failure_message("TradingView rejected the client registration", resp)
        )
    body = resp.json()
    client_id = body.get("client_id") if isinstance(body, dict) else None
    if not client_id:
        raise TradingViewOAuthError("TradingView's registration response had no client_id.")
    return {"client_id": str(client_id), "client_secret": str(body.get("client_secret") or "")}


def _pkce_pair() -> tuple[str, str]:
    verifier = token_urlsafe(64)  # 86 chars — inside RFC 7636's 43..128
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _state_key(state: str) -> str:
    return f"{_STATE_KEY_PREFIX}{state}"


def _store_flow(state: str, flow: dict) -> None:
    """Stash the per-flow secrets (client + PKCE verifier) under a one-time nonce."""
    try:
        _redis().set(_state_key(state), json.dumps(flow), ex=_STATE_TTL_SECONDS)
    except Exception:  # a miss just makes the callback fail closed
        log.warning("Could not store TradingView OAuth state", exc_info=True)


def consume_oauth_state(state: str | None) -> dict | None:
    """Return the flow stored under ``state`` and delete it (one-time use), else None.

    Fails closed on a missing/unknown/empty nonce or any Redis error, so a cross-site
    callback carrying an attacker's code is rejected before token exchange
    (RFC 6749 §10.12). GETDEL is atomic: a concurrent replay wins at most once."""
    if not state:
        return None
    try:
        raw: bytes | None = _redis().getdel(_state_key(state))  # type: ignore[assignment]
    except Exception:
        log.warning("Could not validate TradingView OAuth state", exc_info=True)
        return None
    if not raw:
        return None
    try:
        flow = json.loads(raw)
    except ValueError:
        return None
    return flow if isinstance(flow, dict) else None


def build_authorize_url() -> str:
    """Register a client, mint state + PKCE, stash the flow, return the consent URL."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return f"{settings.TRADINGVIEW_CALLBACK_URL}?code=MOCK_OAUTH&state=mock"

    meta = discover()
    client = register_client(meta)
    verifier, challenge = _pkce_pair()
    state = token_urlsafe(32)
    _store_flow(state, {**client, "code_verifier": verifier})
    params = {
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": settings.TRADINGVIEW_CALLBACK_URL,
        "scope": SCOPE,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "resource": mcp_url(),
    }
    return f"{meta['authorization_endpoint']}?{urlencode(params)}"


# --- tokens ---------------------------------------------------------------------------

_SLEEP = time.sleep  # patch point for the lock-wait test


def _token_request(meta: dict, flow: dict, data: dict) -> dict:
    """POST the token endpoint with the flow's client identity + RFC 8707 resource.

    Raises TradingViewTokenRejected on 400/401 (invalid grant — reconnect), else
    TradingViewOAuthError. Stamps an absolute ``expires_at`` and carries the client ids."""
    form = {**data, "client_id": flow["client_id"], "resource": mcp_url()}
    if flow.get("client_secret"):
        form["client_secret"] = flow["client_secret"]
    try:
        resp = httpx.post(meta["token_endpoint"], data=form, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise TradingViewOAuthError("Could not reach TradingView's token endpoint.") from exc
    if resp.status_code in (400, 401):
        raise TradingViewTokenRejected(_failure_message("TradingView rejected the grant", resp))
    if resp.status_code != 200:
        raise TradingViewOAuthError(_failure_message("TradingView token request failed", resp))
    body = resp.json()
    if not isinstance(body, dict) or not body.get("access_token"):
        raise TradingViewOAuthError("TradingView's token response had no access_token.")
    body["expires_at"] = int(time.time()) + int(body.get("expires_in") or 3600)
    body["client_id"] = flow["client_id"]
    body["client_secret"] = flow.get("client_secret") or ""
    return body


def exchange_code(code: str, flow: dict) -> dict:
    """Exchange the authorization code (PKCE verifier from the stored flow) for tokens."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return {
            "access_token": "mock-tv-access",
            "refresh_token": "mock-tv-refresh",
            "token_type": "Bearer",
            "scope": SCOPE,
            "expires_at": int(time.time()) + 3600,
            "client_id": str(flow.get("client_id") or "mock-client"),
            "client_secret": "",
            "registered_at": int(time.time()),
        }
    token = _token_request(
        discover(),
        flow,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.TRADINGVIEW_CALLBACK_URL,
            "code_verifier": flow["code_verifier"],
        },
    )
    token["registered_at"] = int(time.time())
    return token


def refresh(token: dict) -> dict:
    """Refresh-token grant. A response without a refresh_token keeps the previous one."""
    new = _token_request(
        discover(), token, {"grant_type": "refresh_token", "refresh_token": token["refresh_token"]}
    )
    if not new.get("refresh_token"):
        new["refresh_token"] = token.get("refresh_token", "")
    new["registered_at"] = token.get("registered_at")
    return new


def persist_token(token: dict) -> None:
    """Upsert the TradingView token; self-heals an undecryptable row; clears the marker."""
    from apps.core import provider_health
    from apps.secrets.models import ApiCredential

    expires_at = datetime.fromtimestamp(token["expires_at"], tz=timezone.get_current_timezone())
    try:
        ApiCredential.objects.update_or_create(
            provider="tradingview", defaults={"token": token, "expires_at": expires_at}
        )
    except InvalidToken:
        # The existing row is encrypted under a rotated key: update_or_create's lookup
        # SELECT can't read it. Delete (no decrypt) + create so reconnect self-heals.
        log.warning("Overwriting undecryptable TradingView credential on reconnect.")
        with transaction.atomic():
            ApiCredential.objects.filter(provider="tradingview").delete()
            ApiCredential.objects.create(provider="tradingview", token=token, expires_at=expires_at)
    provider_health.clear_auth_error("tradingview")


def load_token() -> dict | None:
    """The stored token dict, or None when not connected / undecryptable."""
    from apps.secrets.credentials import decrypt_token

    token = decrypt_token("tradingview")
    return token if token and token.get("access_token") else None


def _is_stale(token: dict) -> bool:
    return int(token.get("expires_at") or 0) - int(time.time()) < _REFRESH_SKEW_SECONDS


def _wait_for_other_refresh(stale: dict) -> str | None:
    """Another process holds the refresh lock: poll the row up to 5s for a newer token."""
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        _SLEEP(0.25)
        fresh = load_token()
        if fresh is None:
            return None
        if int(fresh.get("expires_at") or 0) > int(stale.get("expires_at") or 0):
            return str(fresh["access_token"])
    return str(stale.get("access_token") or "") or None


def _refresh_under_lock(token: dict, *, force: bool) -> str | None:
    from apps.core import provider_health

    current = load_token() or token  # another process may have refreshed meanwhile
    if not force and not _is_stale(current):
        return str(current["access_token"])
    try:
        new = refresh(current)
    except TradingViewTokenRejected:
        log.warning("TradingView refused to refresh the stored token; reconnect required.")
        provider_health.mark_auth_error("tradingview", REJECTED_MESSAGE)
        return None
    except TradingViewOAuthError:
        log.warning("TradingView token refresh failed (transient); using the current token.")
        return str(current["access_token"])
    persist_token(new)
    return str(new["access_token"])


def ensure_fresh_token(*, force: bool = False) -> str | None:
    """The access token to send. Refreshes under a Redis lock when < 60s remain (or on
    ``force``, after a 401) so web + worker never double-refresh a rotating refresh
    token. None when not connected or the refresh was rejected (marker recorded)."""
    from apps.core import provider_health

    token = load_token()
    if token is None:
        return None
    if not force and not _is_stale(token):
        return str(token["access_token"])
    if not token.get("refresh_token"):
        provider_health.mark_auth_error("tradingview", REJECTED_MESSAGE)
        return None

    r = _redis()
    try:
        acquired = bool(r.set(_REFRESH_LOCK_KEY, "1", nx=True, ex=_REFRESH_LOCK_TTL_SECONDS))
    except Exception:
        acquired = True  # no lock available: refresh anyway rather than stall every call
    if not acquired:
        return _wait_for_other_refresh(token)
    try:
        return _refresh_under_lock(token, force=force)
    finally:
        try:
            r.delete(_REFRESH_LOCK_KEY)
        except Exception:
            log.debug("Could not release the TradingView refresh lock", exc_info=True)


def revoke_and_disconnect() -> None:
    """Best-effort upstream revocation, then delete the row, clear the marker, and drop
    the process-local MCP session + cached tool list."""
    from apps.core import provider_health
    from apps.core.mocks import is_mock_mode
    from apps.secrets.models import ApiCredential

    token = load_token()
    if token and token.get("refresh_token") and not is_mock_mode():
        try:
            endpoint = discover().get("revocation_endpoint")
            if endpoint:
                httpx.post(
                    endpoint,
                    data={"token": token["refresh_token"], "client_id": token.get("client_id", "")},
                    timeout=_TIMEOUT,
                )
        except Exception:
            log.info("TradingView token revocation skipped (best-effort)", exc_info=True)
    ApiCredential.objects.filter(provider="tradingview").delete()
    provider_health.clear_auth_error("tradingview")
    # lazy: market imports secrets
    from apps.market.services import tradingview_mcp

    tradingview_mcp.reset_state()
