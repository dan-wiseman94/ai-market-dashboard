"""safe_err must never echo a request URL (which carries the API key in the query string)."""

from __future__ import annotations

import requests  # type: ignore[import-untyped]

from apps.market.services.safe_log import safe_err


def test_safe_err_http_error_redacts_url_and_key():
    resp = requests.Response()
    resp.status_code = 401
    exc = requests.HTTPError(
        "401 Client Error: Unauthorized for url: "
        "https://api.stlouisfed.org/fred/series/observations?api_key=SUPERSECRET123",
        response=resp,
    )
    out = safe_err(exc)
    assert "SUPERSECRET123" not in out
    assert "api_key" not in out
    assert "://" not in out  # no URL leaked
    assert out == "HTTPError status=401"


def test_safe_err_connection_error_is_type_name_only():
    exc = requests.ConnectionError(
        "HTTPSConnectionPool(host='api.twelvedata.com', port=443): Max retries exceeded "
        "with url: /quote?symbol=AAPL&apikey=SECRETKEY"
    )
    out = safe_err(exc)
    assert "SECRETKEY" not in out
    assert "apikey" not in out
    assert out == "ConnectionError"


def test_safe_err_plain_exception_is_type_name():
    assert safe_err(ValueError("boom")) == "ValueError"
