"""Best-effort credential validation for the settings "Test" button.

Each keyed provider gets a minimal authenticated probe against its own public host
(hosts are hardcoded per provider — no user input in the URL, so no SSRF surface).
We classify the HTTP response: 200 = works, 400/401/402/403 = key rejected, else =
unexpected. Never raises — returns ``{"ok": bool, "message": str}``. Honors
MOCK_EXTERNAL and never logs the credential.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import requests  # type: ignore[import-untyped]

from apps.market.services.safe_log import safe_err
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)
_TIMEOUT = 8


def _probe_alpaca(t: dict):
    return requests.get(
        "https://data.alpaca.markets/v2/stocks/AAPL/snapshot",
        params={"feed": "iex"},
        headers={
            "APCA-API-KEY-ID": t.get("api_key", ""),
            "APCA-API-SECRET-KEY": t.get("api_secret", ""),
        },
        timeout=_TIMEOUT,
    )


def _probe_finnhub(t: dict):
    return requests.get(
        "https://finnhub.io/api/v1/quote",
        params={"symbol": "AAPL", "token": t.get("api_key", "")},
        timeout=_TIMEOUT,
    )


def _probe_tiingo(t: dict):
    return requests.get(
        "https://api.tiingo.com/api/test",
        headers={"Authorization": f"Token {t.get('api_key', '')}"},
        timeout=_TIMEOUT,
    )


def _probe_twelvedata(t: dict):
    resp = requests.get(
        "https://api.twelvedata.com/quote",
        params={"symbol": "AAPL", "apikey": t.get("api_key", "")},
        timeout=_TIMEOUT,
    )
    # Twelve Data answers HTTP 200 even for a bad key, with the error in the JSON body —
    # normalise that to a 401 here so the classifier stays purely status-code-driven.
    if resp.status_code == 200:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if isinstance(body, dict) and str(body.get("status")) == "error":
            return SimpleNamespace(status_code=401)
    return resp


def _probe_polygon(t: dict):
    return requests.get(
        "https://api.polygon.io/v1/marketstatus/now",
        params={"apiKey": t.get("api_key", "")},
        timeout=_TIMEOUT,
    )


def _probe_tradier(t: dict):
    return requests.get(
        "https://sandbox.tradier.com/v1/markets/quotes",
        params={"symbols": "AAPL"},
        headers={"Authorization": f"Bearer {t.get('api_key', '')}", "Accept": "application/json"},
        timeout=_TIMEOUT,
    )


def _probe_fred(t: dict):
    return requests.get(
        "https://api.stlouisfed.org/fred/series",
        params={"series_id": "GNPCA", "api_key": t.get("api_key", ""), "file_type": "json"},
        timeout=_TIMEOUT,
    )


def _probe_marketaux(t: dict):
    return requests.get(
        "https://api.marketaux.com/v1/news/all",
        params={"api_token": t.get("api_key", ""), "limit": 1},
        timeout=_TIMEOUT,
    )


_PROBES = {
    "alpaca": _probe_alpaca,
    "finnhub": _probe_finnhub,
    "tiingo": _probe_tiingo,
    "twelvedata": _probe_twelvedata,
    "polygon": _probe_polygon,
    "tradier": _probe_tradier,
    "fred": _probe_fred,
    "marketaux": _probe_marketaux,
}


def _classify(resp) -> dict:
    if resp.status_code == 200:
        return {"ok": True, "message": "Key works."}
    if resp.status_code in (400, 401, 402, 403):
        return {"ok": False, "message": f"Key rejected (HTTP {resp.status_code})."}
    return {"ok": False, "message": f"Unexpected response (HTTP {resp.status_code})."}


def test_credential(provider: str) -> dict:
    """Validate the saved credential for ``provider`` with a minimal probe. Never raises."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return {"ok": True, "message": "Mock mode — credential not contacted."}
    probe = _PROBES.get(provider)
    if probe is None:
        return {"ok": False, "message": "Testing isn't supported for this source."}
    try:
        cred = ApiCredential.objects.get(provider=provider)
    except ApiCredential.DoesNotExist:
        return {"ok": False, "message": "No credential saved yet."}
    try:
        resp = probe(cred.token or {})
    except Exception as exc:
        log.warning("market.data_source_test.failed provider=%s: %s", provider, safe_err(exc))
        return {"ok": False, "message": "Couldn't reach the provider."}
    return _classify(resp)
