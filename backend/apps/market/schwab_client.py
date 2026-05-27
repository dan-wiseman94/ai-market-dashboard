"""Schwab client factory.

Uses schwab-py's `client_from_access_functions` so token storage is entirely
under our control (encrypted in Postgres via ApiCredential).
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from django.conf import settings
from schwab.auth import client_from_access_functions

from apps.secrets.schwab_oauth import load_token, persist_token


class SchwabNotConnectedError(RuntimeError):
    """Raised when no Schwab credential exists. Callers should surface this to the UI."""


class SchwabAuthError(SchwabNotConnectedError):
    """A saved credential exists but Schwab rejected it (HTTP 401/403).

    Subclasses SchwabNotConnectedError so the existing ``_wrap_schwab`` view
    decorator turns it into the same 503 "reconnect" response, while carrying a
    message that distinguishes "token rejected" from "never connected".
    """


def schwab_json(resp: Any) -> Any:
    """Parse a schwab-py response, raising on auth rejection before parsing.

    schwab-py hands back ``httpx.Response`` objects. A non-2xx body is a JSON
    *error object*, not the caller's expected payload — parsing it as the
    happy-path shape silently yields empty/garbage data (or, for a top-level
    list, crashes when dict keys are treated as items). Check status first and
    translate 401/403 into ``SchwabAuthError`` so the UI gets its reconnect
    signal; let other HTTP errors propagate as genuine 500s.
    """
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            raise SchwabAuthError(
                f"Schwab rejected the saved credential (HTTP {e.response.status_code}). "
                "Reconnect at /settings."
            ) from e
        raise
    return resp.json()


def _read_token() -> dict | None:
    """Return the token in schwab-py's metadata-wrapped format.

    We persist the *bare* OAuth token (so our own code — the status view, the
    proactive-refresh task — reads its fields directly). schwab-py's
    ``client_from_access_functions`` instead expects a
    ``{"creation_timestamp", "token"}`` wrapper (``TokenMetadata.from_loaded_token``
    raises "token format has changed" without it), so wrap on the way out.
    """
    raw = load_token()
    if raw is None:
        return None
    creation = int(raw.get("creation_timestamp") or time.time())
    return {"creation_timestamp": creation, "token": raw}


def _write_token(token: Any) -> None:
    """Persist a token, accepting either schwab-py's wrapper or a bare token.

    On refresh, schwab-py hands back ``{"creation_timestamp", "token"}``; unwrap
    it and carry the creation timestamp into the stored bare token so a later
    ``_read_token`` re-wraps it faithfully. Also stamps absolute ``expires_at``.
    """
    if isinstance(token, dict) and "token" in token and "creation_timestamp" in token:
        inner = dict(token["token"])
        inner["creation_timestamp"] = int(token["creation_timestamp"])
    else:
        inner = dict(token)
    if "expires_at" not in inner and "expires_in" in inner:
        inner["expires_at"] = int(time.time()) + int(inner["expires_in"])
    persist_token(inner)


# Back-compat factory; tests import _make_write_func and call it.
def _make_write_func():
    return _write_token


def _mock_resp(payload: Any):
    """Stand-in for an httpx.Response: carries .json() and a no-op .raise_for_status().

    The real client returns httpx.Response objects that ``schwab_json`` calls
    ``raise_for_status()`` on; mock responses must honor that contract too.
    """
    import types

    return types.SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)


class _MockSchwabClient:
    """Minimal stand-in for schwab.client.Client used in MOCK_EXTERNAL mode."""

    class Options:
        class ContractType:
            ALL = "ALL"
            CALL = "CALL"
            PUT = "PUT"

    class Account:
        class Fields:
            POSITIONS = "positions"

    def get_quotes(self, tickers):
        return _mock_resp(
            {
                t: {
                    "quote": {
                        "lastPrice": 100.0,
                        "bidPrice": 99.9,
                        "askPrice": 100.1,
                        "totalVolume": 1_000_000,
                        "highPrice": 101.0,
                        "lowPrice": 99.0,
                        "netPercentChange": 0.5,
                    }
                }
                for t in tickers
            }
        )

    def get_option_chain(self, *_args, **_kwargs):
        """Empty-but-well-shaped chain payload — matches the structure ``_normalize_chain`` expects."""
        return _mock_resp(
            {
                "symbol": "MOCK",
                "underlying": {"last": 100.0},
                "callExpDateMap": {},
                "putExpDateMap": {},
            }
        )

    def get_account_numbers(self):
        return _mock_resp([])

    def get_accounts(self, *_args, **_kwargs):
        """Mock-mode positions surface — empty list keeps the positions view at zero."""
        return _mock_resp([])

    def get_movers(self, *_args, **_kwargs):
        return _mock_resp({"screeners": []})

    def __getattr__(self, name: str):
        """Return a callable that yields an empty candles response for any OHLC method."""

        def _mock_ohlc(*_args, **_kwargs):
            return _mock_resp({"candles": []})

        return _mock_ohlc


def get_schwab_client(*, asyncio: bool = False):
    """Return a live schwab.client.Client (or AsyncClient if asyncio=True).

    Raises SchwabNotConnectedError if no credential row exists.
    """
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _MockSchwabClient()

    if load_token() is None:
        raise SchwabNotConnectedError("No Schwab credential; connect at /settings first.")

    return client_from_access_functions(
        api_key=settings.SCHWAB_CLIENT_ID,
        app_secret=settings.SCHWAB_CLIENT_SECRET,
        token_read_func=_read_token,
        token_write_func=_write_token,
        asyncio=asyncio,
    )
