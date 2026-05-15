from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from apps.secrets.models import ApiCredential


@pytest.mark.django_db
@override_settings(
    SCHWAB_CLIENT_ID="cid",
    SCHWAB_CALLBACK_URL="https://127.0.0.1:8000/api/schwab/callback",
    SCHWAB_AUTHORIZE_URL="https://api.schwabapi.com/v1/oauth/authorize",
)
def test_authorize_endpoint_returns_schwab_url():
    client = Client()
    response = client.get("/api/schwab/authorize/")
    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith("https://api.schwabapi.com/v1/oauth/authorize?")
    assert "client_id=cid" in body["url"]


@pytest.mark.django_db
def test_callback_without_code_returns_400():
    client = Client()
    response = client.get("/api/schwab/callback/")
    assert response.status_code == 400
    assert response.json()["code"] == "missing_code"


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
def test_callback_exchanges_code_and_redirects_to_settings():
    with (
        patch("apps.secrets.views.exchange_code_for_token") as ex,
        patch("apps.secrets.views.persist_token") as ps,
    ):
        ex.return_value = {"access_token": "A", "refresh_token": "R", "expires_at": 9999999999}
        client = Client()
        response = client.get("/api/schwab/callback/", {"code": "abc"})
        assert response.status_code == 302
        assert response["Location"] == "/settings?schwab=connected"
        ex.assert_called_once_with("abc")
        ps.assert_called_once()


@pytest.mark.django_db
def test_status_not_connected():
    client = Client()
    response = client.get("/api/schwab/status/")
    assert response.status_code == 200
    assert response.json() == {"connected": False, "expires_at": None}


@pytest.mark.django_db
def test_status_connected():
    future = timezone.now() + timedelta(days=5)
    ApiCredential.objects.create(provider="schwab", token={"access_token": "A"}, expires_at=future)
    client = Client()
    response = client.get("/api/schwab/status/")
    body = response.json()
    assert body["connected"] is True
    assert body["expires_at"] is not None
