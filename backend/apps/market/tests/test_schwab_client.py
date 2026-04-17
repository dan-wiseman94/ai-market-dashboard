from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from datetime import timedelta

from apps.market.schwab_client import get_schwab_client, SchwabNotConnectedError
from apps.secrets.models import ApiCredential


@pytest.mark.django_db
def test_raises_when_not_connected():
    with pytest.raises(SchwabNotConnectedError):
        get_schwab_client()


@pytest.mark.django_db
@override_settings(SCHWAB_CLIENT_ID="cid", SCHWAB_CLIENT_SECRET="csec")
def test_returns_client_when_connected():
    ApiCredential.objects.create(
        provider="schwab",
        token={"access_token": "AT", "refresh_token": "RT", "expires_at": 9999999999, "token_type": "Bearer"},
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
