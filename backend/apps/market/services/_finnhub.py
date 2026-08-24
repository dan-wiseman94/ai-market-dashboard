"""Shared Finnhub HTTP client for the market service modules.

Consumers import these under module-level aliases (``_finnhub_api_key``,
``_finnhub_get``/``_finnhub_get_list``) so tests can patch the name in the
module where it's used.
"""

from __future__ import annotations

import requests  # type: ignore[import-untyped]

from apps.secrets.credentials import decrypt_token

FINNHUB_BASE = "https://finnhub.io/api/v1"


def api_key() -> str | None:
    return (decrypt_token("finnhub") or {}).get("api_key")


def _get_json(path: str, params: dict, api_key: str):
    params = {**params, "token": api_key}
    resp = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_dict(path: str, params: dict, api_key: str) -> dict:
    """GET a Finnhub endpoint that returns a JSON object."""
    body = _get_json(path, params, api_key)
    return body if isinstance(body, dict) else {}


def get_list(path: str, params: dict, api_key: str) -> list:
    """GET a Finnhub endpoint that returns a JSON array."""
    body = _get_json(path, params, api_key)
    return body if isinstance(body, list) else []
