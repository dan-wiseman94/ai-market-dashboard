"""RejectNullBytesMiddleware — NUL (0x00) bytes must 400, not 500.

NUL bytes in any ingress path (path params, an Authorization header reaching
BasicAuthentication, JSON bodies) must 400 before reaching Postgres text columns —
otherwise Postgres raises DataError and it surfaces as a 500.
"""

import pytest
from rest_framework.test import APIClient

NUL = "\x00"


@pytest.mark.django_db
def test_null_byte_in_json_body_returns_400():
    # DRF JSON-encodes the NUL as an escape; the middleware parses + checks the decoded value.
    r = APIClient().post("/api/watchlists/", {"name": f"a{NUL}b"}, format="json")
    assert r.status_code == 400
    assert r.json()["detail"] == "Null bytes are not allowed."


@pytest.mark.django_db
def test_null_byte_in_path_returns_400():
    r = APIClient().get(f"/api/watchlists/a{NUL}b/tickers/")
    assert r.status_code == 400


@pytest.mark.django_db
def test_null_byte_in_authorization_header_returns_400():
    r = APIClient().get("/api/threads/", HTTP_AUTHORIZATION=f"Basic a{NUL}b")
    assert r.status_code == 400


@pytest.mark.django_db
def test_clean_request_is_not_blocked():
    r = APIClient().get("/api/threads/")
    assert r.status_code == 200
