from unittest.mock import MagicMock, patch

import fakeredis
import pytest
from django.test import override_settings

from apps.secrets.models import ApiCredential
from apps.secrets.schwab_oauth import (
    build_authorize_url,
    exchange_code_for_token,
    load_token,
    persist_token,
    refresh_token,
)


@pytest.mark.django_db
def test_persist_token_clears_auth_error_marker():
    """Reconnecting (a fresh, working token) must immediately clear a stale
    auth-error marker so the connection status recovers without a market read or
    waiting out the marker TTL."""
    fake = fakeredis.FakeStrictRedis()
    with patch("apps.core.provider_health._redis", lambda: fake):
        from apps.core import provider_health

        provider_health.mark_auth_error("schwab", "was rejected")
        persist_token({"access_token": "A", "refresh_token": "R", "expires_at": 9999999999})
        assert provider_health.auth_error("schwab") is None


@pytest.mark.django_db
@override_settings(
    SCHWAB_CLIENT_ID="cid",
    SCHWAB_CALLBACK_URL="https://127.0.0.1:8000/api/schwab/callback",
    SCHWAB_AUTHORIZE_URL="https://api.schwabapi.com/v1/oauth/authorize",
)
def test_build_authorize_url_includes_required_params():
    url = build_authorize_url()
    assert url.startswith("https://api.schwabapi.com/v1/oauth/authorize?")
    assert "client_id=cid" in url
    assert "response_type=code" in url
    assert "redirect_uri=https%3A%2F%2F127.0.0.1%3A8000%2Fapi%2Fschwab%2Fcallback" in url


@pytest.mark.django_db
@override_settings(
    SCHWAB_CLIENT_ID="cid",
    SCHWAB_CLIENT_SECRET="csec",
    SCHWAB_CALLBACK_URL="https://127.0.0.1:8000/api/schwab/callback",
    SCHWAB_TOKEN_URL="https://api.schwabapi.com/v1/oauth/token",
)
def test_exchange_code_for_token_posts_correct_body():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "AT",
        "refresh_token": "RT",
        "expires_in": 1800,
        "token_type": "Bearer",
    }
    with patch("apps.secrets.schwab_oauth.httpx.post", return_value=mock_resp) as post:
        tok = exchange_code_for_token("the-code")
        post.assert_called_once()
        _, kwargs = post.call_args
        assert kwargs["data"]["grant_type"] == "authorization_code"
        assert kwargs["data"]["code"] == "the-code"
        assert kwargs["data"]["redirect_uri"] == "https://127.0.0.1:8000/api/schwab/callback"
        assert kwargs["auth"] == ("cid", "csec")
    assert tok["access_token"] == "AT"
    assert tok["refresh_token"] == "RT"
    assert "expires_at" in tok  # our code adds this


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec", SCHWAB_TOKEN_URL="u")
def test_refresh_token_uses_refresh_grant():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "AT2",
        "refresh_token": "RT2",
        "expires_in": 1800,
    }
    with patch("apps.secrets.schwab_oauth.httpx.post", return_value=mock_resp) as post:
        tok = refresh_token("old-refresh")
        _, kwargs = post.call_args
        assert kwargs["data"]["grant_type"] == "refresh_token"
        assert kwargs["data"]["refresh_token"] == "old-refresh"
    assert tok["access_token"] == "AT2"


@pytest.mark.django_db
def test_persist_token_creates_or_updates_credential():
    tok = {"access_token": "A", "refresh_token": "R", "expires_at": 1700000000}
    persist_token(tok)
    cred = ApiCredential.objects.get(provider="schwab")
    assert cred.token["access_token"] == "A"
    # Upsert
    tok2 = {"access_token": "A2", "refresh_token": "R2", "expires_at": 1800000000}
    persist_token(tok2)
    cred.refresh_from_db()
    assert cred.token["access_token"] == "A2"


@pytest.mark.django_db
def test_load_token_returns_none_when_undecryptable():
    """An undecryptable stored token (key rotated / salt reset) must read as None so the
    Schwab client behaves as not-connected instead of raising InvalidToken at call time."""
    from cryptography.fernet import Fernet
    from django.db import connection

    cred = ApiCredential.objects.create(
        provider="schwab", token={"access_token": "A", "refresh_token": "R"}
    )
    foreign = Fernet(Fernet.generate_key()).encrypt(b'{"refresh_token":"R"}')
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_apicredential SET token = %s WHERE id = %s",
            [foreign, cred.id],
        )

    assert load_token() is None


@pytest.mark.django_db
def test_persist_token_overwrites_undecryptable_row():
    """Reconnecting must self-heal a dead row: update_or_create's lookup SELECT can't decrypt
    the old token (InvalidToken), so persist_token falls back to delete+create. This is the
    OAuth-callback 500 that blocked reconnection."""
    from cryptography.fernet import Fernet
    from django.db import connection

    cred = ApiCredential.objects.create(provider="schwab", token={"access_token": "OLD"})
    foreign = Fernet(Fernet.generate_key()).encrypt(b'{"access_token":"OLD"}')
    with connection.cursor() as c:
        c.execute(
            "UPDATE secrets_apicredential SET token = %s WHERE id = %s",
            [foreign, cred.id],
        )

    persist_token({"access_token": "NEW", "refresh_token": "R", "expires_at": 1900000000})

    refreshed = ApiCredential.objects.get(provider="schwab")
    assert refreshed.token["access_token"] == "NEW"
