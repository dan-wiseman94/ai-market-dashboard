"""Schwab client factory.

Uses schwab-py's `client_from_access_functions` so token storage is entirely
under our control (encrypted in Postgres via ApiCredential).
"""
from __future__ import annotations

import time
from typing import Any

from django.conf import settings
from schwab.auth import client_from_access_functions

from apps.secrets.schwab_oauth import load_token, persist_token


class SchwabNotConnectedError(RuntimeError):
    """Raised when no Schwab credential exists. Callers should surface this to the UI."""


def _read_token() -> dict | None:
    return load_token()


def _write_token(token: Any) -> None:
    # schwab-py calls this after refresh; persist_token expects 'expires_at' (unix seconds).
    if "expires_at" not in token and "expires_in" in token:
        token["expires_at"] = int(time.time()) + int(token["expires_in"])
    persist_token(token)


# Back-compat factories; tests import _make_write_func and call it.
def _make_read_func():
    return _read_token


def _make_write_func():
    return _write_token


def get_schwab_client(*, asyncio: bool = False):
    """Return a live schwab.client.Client (or AsyncClient if asyncio=True).

    Raises SchwabNotConnectedError if no credential row exists.
    """
    if load_token() is None:
        raise SchwabNotConnectedError("No Schwab credential; connect at /settings first.")

    return client_from_access_functions(
        api_key=settings.SCHWAB_CLIENT_ID,
        app_secret=settings.SCHWAB_CLIENT_SECRET,
        token_read_func=_read_token,
        token_write_func=_write_token,
        asyncio=asyncio,
    )
