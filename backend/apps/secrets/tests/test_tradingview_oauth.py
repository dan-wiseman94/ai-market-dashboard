"""TradingView MCP OAuth 2.1 client — discovery, registration, PKCE, state, tokens."""

from __future__ import annotations

import base64
import hashlib
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import fakeredis
import httpx
import pytest
from django.test import override_settings

from apps.secrets import tradingview_oauth as tvo

MCP = "https://mcp.tradingview.com/mcp"
CALLBACK = "https://127.0.0.1:8000/api/schwab/data-sources/tradingview/callback/"
AS_META = {
    "issuer": "https://www.tradingview.com",
    "authorization_endpoint": "https://www.tradingview.com/mcp/oauth/authorize",
    "token_endpoint": "https://www.tradingview.com/mcp/oauth/token",
    "registration_endpoint": "https://www.tradingview.com/mcp/oauth/register",
    "revocation_endpoint": "https://www.tradingview.com/mcp/oauth/revoke",
}
PRM = {"resource": MCP, "authorization_servers": ["https://www.tradingview.com"]}


@pytest.fixture
def fake_redis():
    fake = fakeredis.FakeStrictRedis()
    with patch("apps.secrets.tradingview_oauth._redis", lambda: fake):
        yield fake


def _get_by_url(table: dict[str, httpx.Response]):
    def _get(url, **_kw):
        return table.get(url, httpx.Response(404, json={"detail": "Not found"}))

    return _get


def test_protected_resource_metadata_url_is_path_based():
    assert (
        tvo._protected_resource_metadata_url(MCP)
        == "https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp"
    )


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_discover_uses_path_based_document_and_caches(fake_redis):
    table = {
        "https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp": httpx.Response(
            200, json=PRM
        ),
        "https://www.tradingview.com/.well-known/oauth-authorization-server": httpx.Response(
            200, json=AS_META
        ),
    }
    with patch("apps.secrets.tradingview_oauth.httpx.get", side_effect=_get_by_url(table)) as g:
        assert tvo.discover()["token_endpoint"] == AS_META["token_endpoint"]
        assert tvo.discover()["token_endpoint"] == AS_META["token_endpoint"]  # cached
    assert g.call_count == 2
    assert json.loads(fake_redis.get("tradingview:oauth:metadata"))["issuer"] == AS_META["issuer"]


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_discover_falls_back_to_www_authenticate_pointer(fake_redis):
    pointer = "https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp"
    table = {
        pointer: httpx.Response(200, json=PRM),
        "https://www.tradingview.com/.well-known/oauth-authorization-server": httpx.Response(
            200, json=AS_META
        ),
    }
    calls = {"n": 0}

    def _get(url, **_kw):
        calls["n"] += 1
        if calls["n"] == 1:  # first hop: the well-known path answers a non-200
            return httpx.Response(400, json={"detail": "deprecated"})
        return table.get(url, httpx.Response(404))

    challenge = httpx.Response(
        401, headers={"WWW-Authenticate": f'Bearer resource_metadata="{pointer}"'}
    )
    with (
        patch("apps.secrets.tradingview_oauth.httpx.get", side_effect=_get),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=challenge),
    ):
        assert tvo.discover()["authorization_endpoint"] == AS_META["authorization_endpoint"]


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_discover_raises_when_no_authorization_server(fake_redis):
    with (
        patch("apps.secrets.tradingview_oauth.httpx.get", return_value=httpx.Response(404)),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=httpx.Response(401)),
        pytest.raises(tvo.TradingViewOAuthError),
    ):
        tvo.discover()


@override_settings(TRADINGVIEW_CALLBACK_URL=CALLBACK)
def test_register_client_posts_public_client_payload():
    resp = httpx.Response(201, json={"client_id": "cid-1"})
    with patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp) as p:
        out = tvo.register_client(AS_META)
    assert out == {"client_id": "cid-1", "client_secret": ""}
    body = p.call_args.kwargs["json"]
    assert body["redirect_uris"] == [CALLBACK]
    assert body["token_endpoint_auth_method"] == "none"
    assert body["grant_types"] == ["authorization_code", "refresh_token"]
    assert body["scope"] == "mcp:read mcp:tools"


def test_register_client_surfaces_rejection_message():
    resp = httpx.Response(
        400, json={"error": "invalid_redirect_uri", "error_description": "loopback not allowed"}
    )
    with (
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp),
        pytest.raises(tvo.TradingViewOAuthError, match="loopback not allowed"),
    ):
        tvo.register_client(AS_META)


@override_settings(TRADINGVIEW_MCP_URL=MCP, TRADINGVIEW_CALLBACK_URL=CALLBACK)
def test_build_authorize_url_carries_pkce_state_and_resource(fake_redis):
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch(
            "apps.secrets.tradingview_oauth.register_client",
            return_value={"client_id": "cid", "client_secret": ""},
        ),
    ):
        url = tvo.build_authorize_url()
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == AS_META["authorization_endpoint"]
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert q["response_type"] == "code"
    assert q["client_id"] == "cid"
    assert q["redirect_uri"] == CALLBACK
    assert q["scope"] == "mcp:read mcp:tools"
    assert q["code_challenge_method"] == "S256"
    assert q["resource"] == MCP
    flow = tvo.consume_oauth_state(q["state"])
    assert flow["client_id"] == "cid"
    digest = hashlib.sha256(flow["code_verifier"].encode()).digest()
    assert q["code_challenge"] == base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def test_consume_oauth_state_is_one_time_and_fails_closed(fake_redis):
    tvo._store_flow("s1", {"client_id": "c", "code_verifier": "v"})
    assert tvo.consume_oauth_state(None) is None
    assert tvo.consume_oauth_state("wrong") is None
    assert tvo.consume_oauth_state("s1") == {"client_id": "c", "code_verifier": "v"}
    assert tvo.consume_oauth_state("s1") is None  # replay rejected


@override_settings(TRADINGVIEW_CALLBACK_URL=CALLBACK)
def test_build_authorize_url_is_stub_under_mock():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        url = tvo.build_authorize_url()
    assert url == f"{CALLBACK}?code=MOCK_OAUTH&state=mock"
