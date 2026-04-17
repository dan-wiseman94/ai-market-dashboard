from unittest.mock import MagicMock, patch

import pytest
from django.test import override_settings

from apps.secrets.models import ApiCredential
from apps.secrets.schwab_oauth import (
    build_authorize_url,
    exchange_code_for_token,
    persist_token,
    refresh_token,
)


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
