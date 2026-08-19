from datetime import timedelta
from unittest.mock import MagicMock, patch

import fakeredis
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


def _resp_raising(status: int, *, body: str = ""):
    """A response whose raise_for_status() raises HTTPStatusError for `status`."""
    request = httpx.Request("GET", "https://api.schwabapi.com/trader/v1/accounts")
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "err",
        request=request,
        response=httpx.Response(status, request=request, content=body.encode()),
    )
    return resp


@pytest.mark.parametrize("status", [401, 403])
def test_schwab_json_translates_auth_errors(status):
    with pytest.raises(SchwabAuthError):
        schwab_json(_resp_raising(status))


def test_schwab_json_client_not_authorized_points_to_api_products():
    # The Trader-API "Client not authorized" 401 is an app-entitlement problem;
    # the message must not tell the user to reconnect.
    body = '{ "errors": [ { "status":401, "detail": "Client not authorized" } ] }'
    with pytest.raises(SchwabAuthError) as exc:
        schwab_json(_resp_raising(401, body=body))
    msg = str(exc.value)
    assert "developer.schwab.com" in msg
    # Must not steer the user to the (useless-here) reconnect flow.
    assert "/settings" not in msg
    assert "won't help" in msg


def test_schwab_json_generic_401_tells_user_to_reconnect():
    with pytest.raises(SchwabAuthError) as exc:
        schwab_json(_resp_raising(401, body='{"error":"invalid_token"}'))
    assert "Reconnect at /settings" in str(exc.value)


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


@pytest.mark.parametrize("status", [401, 403])
def test_schwab_json_records_auth_error_marker_on_rejection(status):
    # A rejected credential must leave a cross-process marker so the connection
    # status surface can stop claiming "connected" — instead of vanishing into a
    # silent free-provider fallback.
    client = fakeredis.FakeStrictRedis()
    with patch("apps.core.provider_health._redis", lambda: client):
        from apps.core import provider_health

        provider_health.clear_auth_error("schwab")
        with pytest.raises(SchwabAuthError):
            schwab_json(_resp_raising(status, body='{"error":"invalid_token"}'))
        assert provider_health.auth_error("schwab") is not None


def test_schwab_json_clears_auth_error_marker_on_success():
    # A subsequent successful call means the credential works again; the stale
    # marker must clear so the UI recovers without waiting out the TTL.
    client = fakeredis.FakeStrictRedis()
    with patch("apps.core.provider_health._redis", lambda: client):
        from apps.core import provider_health

        provider_health.mark_auth_error("schwab", "previously rejected")
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"ok": True}
        assert schwab_json(resp) == {"ok": True}
        assert provider_health.auth_error("schwab") is None


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
    with patch("apps.market.schwab_client.client_from_access_functions") as factory:
        factory.return_value = object()
        client = get_schwab_client()
        assert client is factory.return_value
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
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
def test_write_func_tolerates_authlib_keyword_args():
    """authlib >=1.6 calls the update_token hook with refresh_token=/access_token=
    keywords, which schwab-py forwards through wrapped_token_write_func to our
    writer. The writer must absorb the extra kwargs and still persist the token.

    Regression: TypeError "_write_token() got an unexpected keyword argument
    'refresh_token'" broke every Schwab refresh after authlib bumped to 1.6.x.
    """
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "OLD", "refresh_token": "RT"},
    )
    from apps.market.schwab_client import _write_token

    # Exactly how authlib/schwab-py invoke the hook: token positional + identifying kwargs.
    _write_token(
        {"access_token": "NEW", "refresh_token": "RT2", "expires_at": 9999999999},
        refresh_token="RT2",
        access_token="NEW",
    )
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
