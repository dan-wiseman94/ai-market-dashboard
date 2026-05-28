"""schwab-oauth-ok scenario drives the OAuth flow without real Schwab HTTP."""

from unittest.mock import patch

from apps.core.mocks import reset_scenario, set_scenario


def test_authorize_url_is_stub_under_mock():
    from apps.secrets.schwab_oauth import build_authorize_url

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        set_scenario("schwab-oauth-ok")
        try:
            url = build_authorize_url()
        finally:
            reset_scenario()
    assert "MOCK_OAUTH" in url


def test_exchange_returns_schwab_shaped_token_under_mock():
    from apps.secrets.schwab_oauth import exchange_code_for_token

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        set_scenario("schwab-oauth-ok")
        try:
            token = exchange_code_for_token("AUTHCODE")
        finally:
            reset_scenario()
    # Mapped onto the schwab-py token shape the persistence layer expects.
    assert token["access_token"]
    assert token["refresh_token"]
    assert "expires_at" in token


def test_authorize_url_falls_back_to_stub_under_default():
    from apps.secrets.schwab_oauth import build_authorize_url

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        reset_scenario()
        url = build_authorize_url()
    assert "MOCK_OAUTH" in url
