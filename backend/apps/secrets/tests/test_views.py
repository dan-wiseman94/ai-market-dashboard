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
@override_settings(SCHWAB_CLIENT_ID="")
def test_authorize_returns_400_when_not_configured():
    """With no SCHWAB_CLIENT_ID, don't emit an authorize URL with an empty client_id
    (Schwab bounces it back as 401 invalid_client). Return a clear, structured error so
    the UI can tell the user to set their credentials."""
    client = Client()
    response = client.get("/api/schwab/authorize/")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "schwab_not_configured"
    assert "SCHWAB_CLIENT_ID" in body["message"]


@pytest.mark.django_db
def test_callback_without_code_returns_400():
    client = Client()
    response = client.get("/api/schwab/callback/")
    assert response.status_code == 400
    assert response.json()["code"] == "missing_code"


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
@override_settings(FRONTEND_BASE_URL="https://app.test")
def test_callback_with_valid_state_exchanges_code_and_redirects():
    import fakeredis

    fake = fakeredis.FakeStrictRedis()
    with (
        patch("apps.secrets.schwab_oauth._redis", lambda: fake),
        patch("apps.secrets.views.exchange_code_for_token") as ex,
        patch("apps.secrets.views.persist_token") as ps,
    ):
        from apps.secrets.schwab_oauth import new_oauth_state

        state = new_oauth_state()  # mints + stores the nonce, as the authorize step does
        ex.return_value = {"access_token": "A", "refresh_token": "R", "expires_at": 9999999999}
        client = Client()
        response = client.get("/api/schwab/callback/", {"code": "abc", "state": state})
        assert response.status_code == 302
        # Redirect is prefixed with FRONTEND_BASE_URL so the dev callback (arriving via the
        # tls-proxy on :8000) bounces to the Vite SPA; empty base → same-origin /settings.
        assert response["Location"] == "https://app.test/settings?schwab=connected"
        ex.assert_called_once_with("abc")
        ps.assert_called_once()


@pytest.mark.django_db
def test_callback_rejects_missing_state():
    """A cross-site GET to the callback with an attacker's code but no state nonce we
    minted must be rejected BEFORE any token exchange — the OAuth login-CSRF /
    auth-code-injection hole (RFC 6749 §10.12). The callback is a no-auth-cookie GET, so
    CSRF middleware / SameSite don't cover it."""
    import fakeredis

    fake = fakeredis.FakeStrictRedis()
    with (
        patch("apps.secrets.schwab_oauth._redis", lambda: fake),
        patch("apps.secrets.views.exchange_code_for_token") as ex,
    ):
        client = Client()
        response = client.get("/api/schwab/callback/", {"code": "attacker_code"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_state"
        ex.assert_not_called()  # never exchange an unsolicited authorization code


@pytest.mark.django_db
def test_callback_rejects_mismatched_state():
    """A forged state that doesn't match the minted nonce is rejected."""
    import fakeredis

    fake = fakeredis.FakeStrictRedis()
    with (
        patch("apps.secrets.schwab_oauth._redis", lambda: fake),
        patch("apps.secrets.views.exchange_code_for_token") as ex,
    ):
        from apps.secrets.schwab_oauth import new_oauth_state

        new_oauth_state()  # a real nonce exists, but the callback presents a different one
        client = Client()
        response = client.get("/api/schwab/callback/", {"code": "abc", "state": "forged"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_state"
        ex.assert_not_called()


@pytest.mark.django_db
def test_status_not_connected():
    client = Client()
    response = client.get("/api/schwab/status/")
    assert response.status_code == 200
    assert response.json() == {"connected": False, "expires_at": None, "auth_error": None}


@pytest.mark.django_db
def test_status_surfaces_schwab_auth_error():
    """A revoked/expired OAuth token (Schwab 401/403) must stop masquerading as a
    clean connection: the status surface reports the recorded auth-error message so
    the user knows their reads have silently fallen back to a free provider."""
    import fakeredis

    fake = fakeredis.FakeStrictRedis()
    future = timezone.now() + timedelta(days=5)
    ApiCredential.objects.create(provider="schwab", token={"access_token": "A"}, expires_at=future)
    with patch("apps.core.provider_health._redis", lambda: fake):
        from apps.core import provider_health

        provider_health.mark_auth_error(
            "schwab", "Schwab rejected the stored authorization. Reconnect at /settings."
        )
        client = Client()
        body = client.get("/api/schwab/status/").json()
    # A credential row still exists, so connected stays True — but auth_error carries the truth.
    assert body["connected"] is True
    assert "Reconnect" in (body["auth_error"] or "")


@pytest.mark.django_db
def test_status_connected():
    future = timezone.now() + timedelta(days=5)
    ApiCredential.objects.create(provider="schwab", token={"access_token": "A"}, expires_at=future)
    client = Client()
    response = client.get("/api/schwab/status/")
    body = response.json()
    assert body["connected"] is True
    assert body["expires_at"] is not None


@pytest.mark.django_db
def test_status_reports_not_connected_when_token_undecryptable():
    """A credential encrypted under a now-gone key (DJANGO_SECRET_KEY rotated / salt reset)
    must report not-connected, not 500. Decryption fires during the .get() row fetch via
    EncryptedJSONField.from_db_value; the view has to catch InvalidToken. Reconnecting
    Schwab overwrites the dead row."""
    from cryptography.fernet import Fernet
    from django.db import connection

    cred = ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "A"},
        expires_at=timezone.now() + timedelta(days=5),
    )
    # Clobber the column with ciphertext from a foreign key the current Fernet can't read.
    foreign = Fernet(Fernet.generate_key()).encrypt(b'{"access_token":"A"}')
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_apicredential SET token = %s WHERE id = %s",
            [foreign, cred.id],
        )

    client = Client()
    response = client.get("/api/schwab/status/")
    assert response.status_code == 200
    assert response.json() == {"connected": False, "expires_at": None, "auth_error": None}
