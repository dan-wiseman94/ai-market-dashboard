from datetime import timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.test import override_settings
from django.utils import timezone

from apps.market.schwab_client import (
    SchwabAuthError,
    SchwabNotConnectedError,
    _MockSchwabClient,
    get_schwab_client,
    schwab_json,
)
from apps.secrets.models import ApiCredential


def _resp_raising(status: int):
    """A response whose raise_for_status() raises HTTPStatusError for `status`."""
    request = httpx.Request("GET", "https://api.schwabapi.com/trader/v1/accounts")
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "err", request=request, response=httpx.Response(status, request=request)
    )
    return resp


@pytest.mark.parametrize("status", [401, 403])
def test_schwab_json_translates_auth_errors(status):
    with pytest.raises(SchwabAuthError):
        schwab_json(_resp_raising(status))


def test_schwab_json_propagates_other_http_errors():
    # A 500 is a genuine upstream failure, not a reconnect signal — let it surface.
    with pytest.raises(httpx.HTTPStatusError):
        schwab_json(_resp_raising(500))


def test_schwab_json_returns_body_on_success():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"ok": True}
    assert schwab_json(resp) == {"ok": True}


def test_mock_client_responses_survive_schwab_json():
    # MOCK_EXTERNAL responses must honor the raise_for_status() contract.
    client = _MockSchwabClient()
    assert schwab_json(client.get_accounts()) == []
    assert schwab_json(client.get_quotes(["SPY"]))["SPY"]["quote"]["lastPrice"] == 100.0


@pytest.mark.django_db
def test_raises_when_not_connected():
    with pytest.raises(SchwabNotConnectedError):
        get_schwab_client()


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
def test_returns_client_when_connected():
    ApiCredential.objects.create(
        provider="schwab",
        token={
            "access_token": "AT",
            "refresh_token": "RT",
            "expires_at": 9999999999,
            "token_type": "Bearer",
        },
        expires_at=timezone.now() + timedelta(hours=1),
    )
    # Mock the schwab-py factory so we don't need real credentials
    with patch("apps.market.schwab_client.client_from_access_functions") as factory:
        factory.return_value = object()
        client = get_schwab_client()
        assert client is factory.return_value
        # Verify factory called with client id + secret + read/write funcs
        args, kwargs = factory.call_args
        assert kwargs.get("api_key") == "cid" or (args and args[0] == "cid")


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
def test_write_func_persists_refreshed_token():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "OLD", "refresh_token": "RT"},
    )
    from apps.market.schwab_client import _make_write_func

    write = _make_write_func()
    write({"access_token": "NEW", "refresh_token": "RT2", "expires_at": 9999999999})
    cred = ApiCredential.objects.get(provider="schwab")
    assert cred.token["access_token"] == "NEW"
    assert cred.token["refresh_token"] == "RT2"


@pytest.mark.django_db
def test_read_func_wraps_bare_token_in_schwab_metadata():
    # schwab-py's client_from_access_functions requires the {creation_timestamp, token}
    # wrapper; reading must produce it from our bare stored token.
    from apps.market.schwab_client import _read_token

    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "AT", "refresh_token": "RT", "expires_at": 9999999999},
    )
    wrapped = _read_token()
    assert wrapped is not None
    assert set(wrapped) == {"creation_timestamp", "token"}
    assert isinstance(wrapped["creation_timestamp"], int)
    assert wrapped["token"]["access_token"] == "AT"


@pytest.mark.django_db
def test_write_func_unwraps_schwab_metadata_token():
    # On refresh schwab-py hands back the metadata wrapper; we must unwrap and store
    # the bare token, preserving the creation timestamp.
    from apps.market.schwab_client import _write_token

    _write_token(
        {
            "creation_timestamp": 1700000000,
            "token": {"access_token": "NEW", "refresh_token": "RT2", "expires_at": 9999999999},
        }
    )
    cred = ApiCredential.objects.get(provider="schwab")
    assert cred.token["access_token"] == "NEW"
    assert cred.token["creation_timestamp"] == 1700000000
