"""TradingView MCP OAuth 2.1 client — discovery, registration, PKCE, state, tokens."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import fakeredis
import httpx
import pytest
from django.test import override_settings

from apps.secrets import tradingview_oauth as tvo
from apps.secrets.models import ApiCredential

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


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_discover_rejects_a_non_https_endpoint(fake_redis):
    bad_meta = {**AS_META, "token_endpoint": "http://www.tradingview.com/mcp/oauth/token"}
    table = {
        "https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp": httpx.Response(
            200, json=PRM
        ),
        "https://www.tradingview.com/.well-known/oauth-authorization-server": httpx.Response(
            200, json=bad_meta
        ),
    }
    with (
        patch("apps.secrets.tradingview_oauth.httpx.get", side_effect=_get_by_url(table)),
        pytest.raises(tvo.TradingViewOAuthError, match="https"),
    ):
        tvo.discover()


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_discover_falls_back_to_discovery_when_cache_is_corrupt(fake_redis):
    fake_redis.set(tvo._METADATA_KEY, b"not-json{{{")
    table = {
        "https://mcp.tradingview.com/.well-known/oauth-protected-resource/mcp": httpx.Response(
            200, json=PRM
        ),
        "https://www.tradingview.com/.well-known/oauth-authorization-server": httpx.Response(
            200, json=AS_META
        ),
    }
    with patch("apps.secrets.tradingview_oauth.httpx.get", side_effect=_get_by_url(table)):
        assert tvo.discover()["token_endpoint"] == AS_META["token_endpoint"]


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


def test_register_client_raises_on_non_json_response():
    resp = httpx.Response(201, content=b"not json")
    with (
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp),
        pytest.raises(tvo.TradingViewOAuthError, match="not JSON"),
    ):
        tvo.register_client(AS_META)


def test_failure_message_scrubs_secret_params_and_caps_length():
    long_detail = "reason apikey=SECRET123 then " + ("x" * 300)
    resp = httpx.Response(400, json={"error_description": long_detail})
    msg = tvo._failure_message("TradingView rejected the grant", resp)
    assert "SECRET123" not in msg
    assert "apikey=***" in msg
    detail_part = msg.split(": ", 1)[1]
    assert len(detail_part) == 200


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


FLOW = {"client_id": "cid", "client_secret": "", "code_verifier": "verifier"}


def _token(**over) -> dict:
    base = {
        "access_token": "A",
        "refresh_token": "R",
        "token_type": "Bearer",
        "scope": "mcp:read mcp:tools",
        "expires_at": int(time.time()) + 3600,
        "client_id": "cid",
        "client_secret": "",
        "registered_at": 1,
    }
    return {**base, **over}


@override_settings(TRADINGVIEW_MCP_URL=MCP, TRADINGVIEW_CALLBACK_URL=CALLBACK)
def test_exchange_code_posts_pkce_verifier_client_id_and_resource():
    resp = httpx.Response(200, json={"access_token": "A", "refresh_token": "R", "expires_in": 1800})
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp) as p,
    ):
        token = tvo.exchange_code("CODE", FLOW)
    form = p.call_args.kwargs["data"]
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "CODE"
    assert form["code_verifier"] == "verifier"
    assert form["client_id"] == "cid"
    assert form["redirect_uri"] == CALLBACK
    assert form["resource"] == MCP
    assert "client_secret" not in form
    assert token["access_token"] == "A" and token["client_id"] == "cid"
    assert token["expires_at"] >= int(time.time()) + 1700
    assert token["registered_at"] > 0


@override_settings(TRADINGVIEW_MCP_URL=MCP)
def test_refresh_keeps_previous_refresh_token_when_omitted():
    resp = httpx.Response(200, json={"access_token": "A2", "expires_in": 3600})
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp) as p,
    ):
        new = tvo.refresh(_token())
    assert p.call_args.kwargs["data"]["grant_type"] == "refresh_token"
    assert p.call_args.kwargs["data"]["refresh_token"] == "R"
    assert new["access_token"] == "A2" and new["refresh_token"] == "R"
    assert new["registered_at"] == 1


@override_settings(TRADINGVIEW_MCP_URL=MCP)
@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (400, tvo.TradingViewTokenRejected),
        (401, tvo.TradingViewTokenRejected),
        (503, tvo.TradingViewOAuthError),
    ],
)
def test_token_endpoint_failures_classify(status, exc):
    resp = httpx.Response(status, json={"error": "invalid_grant"})
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.httpx.post", return_value=resp),
        pytest.raises(exc),
    ):
        tvo.refresh(_token())


@pytest.mark.django_db
def test_persist_token_upserts_and_clears_marker():
    fake = fakeredis.FakeStrictRedis()
    with patch("apps.core.provider_health._redis", lambda: fake):
        from apps.core import provider_health

        provider_health.mark_auth_error("tradingview", "was rejected")
        tvo.persist_token(_token())
        tvo.persist_token(_token(access_token="B"))
        assert provider_health.auth_error("tradingview") is None
    cred = ApiCredential.objects.get(provider="tradingview")
    assert cred.token["access_token"] == "B"
    assert cred.expires_at is not None


@pytest.mark.django_db
def test_persist_token_self_heals_undecryptable_row():
    from cryptography.fernet import InvalidToken

    with patch(
        "apps.secrets.models.ApiCredential.objects.update_or_create",
        side_effect=InvalidToken,
    ):
        tvo.persist_token(_token())
    assert ApiCredential.objects.get(provider="tradingview").token["access_token"] == "A"


@pytest.mark.django_db
def test_load_token_none_when_not_connected():
    assert tvo.load_token() is None


@pytest.mark.django_db
def test_ensure_fresh_token_returns_token_when_fresh_without_refresh(fake_redis):
    tvo.persist_token(_token())
    with patch("apps.secrets.tradingview_oauth.refresh") as r:
        assert tvo.ensure_fresh_token() == "A"
    r.assert_not_called()


@pytest.mark.django_db
def test_ensure_fresh_token_refreshes_when_stale_and_persists(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch(
            "apps.secrets.tradingview_oauth.refresh", return_value=_token(access_token="A2")
        ) as r,
    ):
        assert tvo.ensure_fresh_token() == "A2"
    r.assert_called_once()
    assert ApiCredential.objects.get(provider="tradingview").token["access_token"] == "A2"
    assert fake_redis.get("tradingview:oauth:refresh_lock") is None  # lock released


@pytest.mark.django_db
def test_ensure_fresh_token_force_refreshes_a_fresh_token(fake_redis):
    tvo.persist_token(_token())
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth.refresh", return_value=_token(access_token="A3")),
    ):
        assert tvo.ensure_fresh_token(force=True) == "A3"


@pytest.mark.django_db
def test_ensure_fresh_token_rejected_refresh_marks_auth_error(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    with (
        patch("apps.core.provider_health._redis", lambda: fake_redis),
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch(
            "apps.secrets.tradingview_oauth.refresh",
            side_effect=tvo.TradingViewTokenRejected("nope"),
        ),
    ):
        assert tvo.ensure_fresh_token() is None
        from apps.core import provider_health

        assert provider_health.auth_error("tradingview") == tvo.REJECTED_MESSAGE


@pytest.mark.django_db
def test_ensure_fresh_token_transient_refresh_failure_keeps_current(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch(
            "apps.secrets.tradingview_oauth.refresh", side_effect=tvo.TradingViewOAuthError("down")
        ),
    ):
        assert tvo.ensure_fresh_token() == "A"


@pytest.mark.django_db
def test_ensure_fresh_token_transient_discovery_failure_keeps_current(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    with (
        patch(
            "apps.secrets.tradingview_oauth.discover",
            side_effect=tvo.TradingViewOAuthError("down"),
        ),
        patch("apps.secrets.tradingview_oauth.refresh") as r,
    ):
        assert tvo.ensure_fresh_token() == "A"
    r.assert_not_called()


@pytest.mark.django_db
def test_ensure_fresh_token_waits_for_other_process_when_locked(fake_redis):
    tvo.persist_token(_token(expires_at=int(time.time()) + 10))
    fake_redis.set("tradingview:oauth:refresh_lock", "1", ex=30)

    def _other_process_refreshes(_seconds):
        tvo.persist_token(_token(access_token="FROM-OTHER", expires_at=int(time.time()) + 3600))

    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch("apps.secrets.tradingview_oauth._SLEEP", side_effect=_other_process_refreshes),
        patch("apps.secrets.tradingview_oauth.refresh") as r,
    ):
        assert tvo.ensure_fresh_token() == "FROM-OTHER"
    r.assert_not_called()


@pytest.mark.django_db
def test_refresh_under_lock_returns_rotated_token_without_refreshing_even_forced(fake_redis):
    stale = _token(access_token="OLD", expires_at=int(time.time()) + 10)
    tvo.persist_token(_token(access_token="ROTATED", expires_at=int(time.time()) + 3600))
    with patch("apps.secrets.tradingview_oauth.refresh") as r:
        out = tvo._refresh_under_lock(stale, force=True, meta=AS_META)
    assert out == "ROTATED"
    r.assert_not_called()


def test_release_lock_is_a_noop_when_the_value_mismatches(fake_redis):
    fake_redis.set(tvo._REFRESH_LOCK_KEY, "someone-elses-value", ex=120)
    tvo._release_lock("our-value")
    assert fake_redis.get(tvo._REFRESH_LOCK_KEY) == b"someone-elses-value"


def test_release_lock_deletes_when_the_value_matches(fake_redis):
    fake_redis.set(tvo._REFRESH_LOCK_KEY, "our-value", ex=120)
    tvo._release_lock("our-value")
    assert fake_redis.get(tvo._REFRESH_LOCK_KEY) is None


@pytest.mark.django_db
def test_wait_for_other_refresh_times_out_to_stale_token(fake_redis):
    stale = _token(access_token="STALE", expires_at=int(time.time()) + 10)
    tvo.persist_token(stale)
    times = iter([0.0, 0.1, 5.1])  # 3rd check exceeds the 5.0s deadline
    with (
        patch("apps.secrets.tradingview_oauth._SLEEP", return_value=None),
        patch("apps.secrets.tradingview_oauth.time.monotonic", side_effect=lambda: next(times)),
    ):
        out = tvo._wait_for_other_refresh(stale)
    assert out == "STALE"


@pytest.mark.django_db
def test_revoke_and_disconnect_deletes_row_even_if_revocation_fails(fake_redis):
    tvo.persist_token(_token())
    with (
        patch("apps.secrets.tradingview_oauth.discover", return_value=AS_META),
        patch(
            "apps.secrets.tradingview_oauth.httpx.post", side_effect=httpx.ConnectError("x")
        ) as p,
        patch("apps.market.services.tradingview_mcp.reset_state") as reset,
    ):
        tvo.revoke_and_disconnect()
    assert p.call_args.kwargs["data"] == {"token": "R", "client_id": "cid"}
    assert not ApiCredential.objects.filter(provider="tradingview").exists()
    reset.assert_called_once()


@pytest.mark.django_db
def test_exchange_code_is_canned_under_mock():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        token = tvo.exchange_code("MOCK_OAUTH", {"client_id": "mock", "code_verifier": "v"})
    assert token["access_token"] and token["refresh_token"] and token["expires_at"]
