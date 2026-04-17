"""Schwab client factory.

Uses schwab-py's `client_from_access_functions` so token storage is entirely
under our control (encrypted in Postgres via ApiCredential). Token refreshes
are written back through `_make_write_func`.
"""
from __future__ import annotations

from typing import Any

from django.conf import settings
from schwab.auth import client_from_access_functions

from apps.secrets.schwab_oauth import load_token, persist_token


class SchwabNotConnectedError(RuntimeError):
    """Raised when no Schwab credential exists. Callers should surface this to the UI."""


def _make_read_func():
    def read() -> dict | None:
        return load_token()
    return read


def _make_write_func():
    def write(token: Any) -> None:
        # schwab-py calls this with the raw token dict after refresh.
        # Our persist_token expects an 'expires_at' field (unix seconds).
        if "expires_at" not in token and "expires_in" in token:
            import time
            token["expires_at"] = int(time.time()) + int(token["expires_in"])
        persist_token(token)
    return write


def get_schwab_client(*, asyncio: bool = False):
    """Return a live schwab.client.Client (or AsyncClient if asyncio=True).

    Raises SchwabNotConnectedError if no credential row exists.
    """
    if load_token() is None:
        raise SchwabNotConnectedError("No Schwab credential; connect at /settings first.")

    return client_from_access_functions(
        api_key=settings.SCHWAB_CLIENT_ID,
        app_secret=settings.SCHWAB_CLIENT_SECRET,
        token_read_func=_make_read_func(),
        token_write_func=_make_write_func(),
        asyncio=asyncio,
    )
