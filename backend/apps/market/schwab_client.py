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
        import types

        mock_data = {
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
        resp = types.SimpleNamespace(json=lambda: mock_data)
        return resp

    def get_option_chain(self, *_args, **_kwargs):
        """Empty-but-well-shaped chain payload — matches the structure ``_normalize_chain`` expects."""
        import types

        return types.SimpleNamespace(
            json=lambda: {
                "symbol": "MOCK",
                "underlying": {"last": 100.0},
                "callExpDateMap": {},
                "putExpDateMap": {},
            }
        )

    def get_account_numbers(self):
        import types

        return types.SimpleNamespace(json=lambda: [])

    def get_accounts(self, *_args, **_kwargs):
        """Mock-mode positions surface — empty list keeps the positions view at zero."""
        import types

        return types.SimpleNamespace(json=lambda: [])

    def get_movers(self, *_args, **_kwargs):
        import types

        return types.SimpleNamespace(json=lambda: {"screeners": []})

    def __getattr__(self, name: str):
        """Return a callable that yields an empty candles response for any OHLC method."""

        def _mock_ohlc(*_args, **_kwargs):
            import types

            return types.SimpleNamespace(json=lambda: {"candles": []})

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
