"""TradingView MCP transport: JSON + SSE responses, session id, 401/404 retry, tool results."""

from __future__ import annotations

import json
import threading
from unittest.mock import patch

import fakeredis
import httpx
import pytest

from apps.market.services import tradingview_mcp as mcp

_PASSTHRU = {"side_effect": lambda key, *, ttl_seconds, fetcher: fetcher()}


@pytest.fixture(autouse=True)
def _fresh_state():
    fake = fakeredis.FakeStrictRedis()
    with (
        patch("apps.market.services.tradingview_mcp._redis", lambda: fake),
        patch("apps.market.services.tradingview_mcp.cache.get_or_fetch", **_PASSTHRU),
        patch("apps.market.services.tradingview_mcp.oauth.ensure_fresh_token", return_value="tok"),
    ):
        mcp.reset_state()
        yield
        mcp.reset_state()


def _rpc(rpc_id, result=None, error=None, **headers):
    body = {"jsonrpc": "2.0", "id": rpc_id}
    body["error" if error else "result"] = error or (result if result is not None else {})
    return httpx.Response(200, json=body, headers=headers)


class _Server:
    """Scripted httpx.post: answers initialize/initialized/tools calls in order."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.headers: list[dict] = []

    def __call__(self, url, *, json, headers, timeout):
        self.requests.append(json)
        self.headers.append(dict(headers))
        resp = self.responses.pop(0)
        return resp(json) if callable(resp) else resp


def _answer(result):
    return lambda req: _rpc(req["id"], result)


def test_call_tool_parses_json_response_and_sends_headers():
    server = _Server(
        [
            lambda req: _rpc(
                req["id"], {"protocolVersion": "2025-06-18"}, **{"Mcp-Session-Id": "s-1"}
            ),
            httpx.Response(202),
            _answer({"content": [{"type": "text", "text": json.dumps({"bars": [1, 2]})}]}),
        ]
    )
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        out = mcp.call_tool("get_ohlcv", {"symbol": "NASDAQ:AAPL"})
    assert out == {"bars": [1, 2]}
    assert [r["method"] for r in server.requests] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]
    last = server.headers[-1]
    assert last["Authorization"] == "Bearer tok"
    assert last["Accept"] == "application/json, text/event-stream"
    assert last["MCP-Protocol-Version"] == "2025-06-18"
    assert last["Mcp-Session-Id"] == "s-1"
    assert server.requests[-1]["params"] == {
        "name": "get_ohlcv",
        "arguments": {"symbol": "NASDAQ:AAPL"},
    }


def test_sse_response_picks_the_message_answering_our_id():
    def sse(req):
        body = (
            'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress","params":{}}\n\n'
            f"data: {json.dumps({'jsonrpc': '2.0', 'id': req['id'], 'result': {'structuredContent': {'ok': 1}}})}\n\n"
        )
        return httpx.Response(
            200, content=body.encode(), headers={"Content-Type": "text/event-stream"}
        )

    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), sse])
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == {"ok": 1}


def test_stateless_server_initializes_once_per_process():
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            _answer({"content": [{"type": "text", "text": "a"}]}),
            _answer({"content": [{"type": "text", "text": "b"}]}),
        ]
    )
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == "a"
        assert mcp.call_tool("x") == "b"
    assert [r["method"] for r in server.requests].count("initialize") == 1


def test_404_reinitializes_once_and_retries():
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}, **{"Mcp-Session-Id": "old"}),
            httpx.Response(202),
            httpx.Response(404),
            lambda req: _rpc(req["id"], {}, **{"Mcp-Session-Id": "new"}),
            httpx.Response(202),
            _answer({"content": [{"type": "text", "text": "ok"}]}),
        ]
    )
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == "ok"
    assert server.headers[-1]["Mcp-Session-Id"] == "new"


def test_401_forces_one_refresh_and_retry():
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            httpx.Response(401),
            _answer({"content": [{"type": "text", "text": "ok"}]}),
        ]
    )
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        patch(
            "apps.market.services.tradingview_mcp.oauth.ensure_fresh_token",
            side_effect=["tok", "tok2"],
        ) as e,
    ):
        assert mcp.call_tool("x") == "ok"
    assert e.call_args_list[-1].kwargs == {"force": True}
    assert server.headers[-1]["Authorization"] == "Bearer tok2"


def test_second_401_marks_auth_error_and_raises_not_connected():
    fake = fakeredis.FakeStrictRedis()
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            httpx.Response(401),
            httpx.Response(401),
        ]
    )
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        patch("apps.core.provider_health._redis", lambda: fake),
    ):
        with pytest.raises(mcp.TradingViewNotConnected):
            mcp.call_tool("x")
        from apps.core import provider_health

        assert provider_health.auth_error("tradingview") is not None


def test_second_401_with_session_retries_once_more_then_succeeds():
    """A session id was in use when the 2nd 401 lands: forget the session and allow
    exactly one more attempt (re-init) on the SAME token before giving up."""
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}, **{"Mcp-Session-Id": "s-1"}),
            httpx.Response(202),
            httpx.Response(401),
            httpx.Response(401),
            lambda req: _rpc(req["id"], {}, **{"Mcp-Session-Id": "s-2"}),
            httpx.Response(202),
            _answer({"content": [{"type": "text", "text": "ok"}]}),
        ]
    )
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == "ok"
    assert [r["method"] for r in server.requests] == [
        "initialize",
        "notifications/initialized",
        "tools/call",
        "tools/call",
        "initialize",
        "notifications/initialized",
        "tools/call",
    ]
    assert server.headers[-1]["Mcp-Session-Id"] == "s-2"


def test_third_401_after_session_retry_marks_auth_error_and_raises():
    fake = fakeredis.FakeStrictRedis()
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}, **{"Mcp-Session-Id": "s-1"}),
            httpx.Response(202),
            httpx.Response(401),
            httpx.Response(401),
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            httpx.Response(401),
        ]
    )
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        patch("apps.core.provider_health._redis", lambda: fake),
    ):
        with pytest.raises(mcp.TradingViewNotConnected):
            mcp.call_tool("x")
        from apps.core import provider_health

        assert provider_health.auth_error("tradingview") is not None
    assert len(server.requests) == 7


def test_not_connected_raises_without_http():
    with (
        patch("apps.market.services.tradingview_mcp.oauth.ensure_fresh_token", return_value=None),
        patch("apps.market.services.tradingview_mcp.httpx.post") as p,
        pytest.raises(mcp.TradingViewNotConnected),
    ):
        mcp.call_tool("x")
    p.assert_not_called()


def test_429_raises_rate_limited_without_retry():
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), httpx.Response(429)])
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        pytest.raises(mcp.TradingViewRateLimited),
    ):
        mcp.call_tool("x")
    assert len(server.requests) == 3


def test_429_sets_rate_limit_marker_and_reset_state_clears_it():
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), httpx.Response(429)])
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        pytest.raises(mcp.TradingViewRateLimited),
    ):
        mcp.call_tool("x")
    assert mcp.is_rate_limited() is True
    mcp.reset_state()
    assert mcp.is_rate_limited() is False


def test_generic_http_error_raises_mcp_error_without_retry():
    server = _Server([lambda req: _rpc(req["id"], {}), httpx.Response(202), httpx.Response(500)])
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        pytest.raises(mcp.TradingViewMCPError, match="500"),
    ):
        mcp.call_tool("x")
    assert len(server.requests) == 3


def test_forget_session_blocks_until_initialize_releases_the_lock():
    """`_forget_session()` and `_send`'s initialize-bootstrap share ``_session_lock``:
    a call to `_forget_session()` while another thread is inside `_initialize` (holding
    the lock) must block until that thread releases it, rather than racing it to mutate
    `_state`. Synchronized entirely via threading.Event + the lock itself — the short
    `wait()`/`join()` timeouts are assertion polls, not the ordering mechanism (ordering
    is guaranteed by `_session_lock` being held for the whole duration)."""
    started = threading.Event()
    proceed = threading.Event()
    forgotten = threading.Event()

    def fake_initialize(_token):
        started.set()
        assert proceed.wait(timeout=5), "test setup: proceed was never signalled"
        mcp._state["session_id"] = "s-1"
        mcp._state["initialized"] = True

    def bootstrap():
        with mcp._session_lock:
            if not mcp._state["initialized"]:
                mcp._initialize("tok")

    def forget():
        mcp._forget_session()
        forgotten.set()

    with patch("apps.market.services.tradingview_mcp._initialize", side_effect=fake_initialize):
        t1 = threading.Thread(target=bootstrap)
        t1.start()
        assert started.wait(timeout=5), "initialize never started"

        # By now t1 has entered `with _session_lock:` and is blocked inside
        # fake_initialize, so the lock is provably held by another thread.
        acquired = mcp._session_lock.acquire(blocking=False)
        if acquired:
            mcp._session_lock.release()
        assert not acquired

        t2 = threading.Thread(target=forget)
        t2.start()
        # t2 cannot possibly finish yet: the lock stays held until `proceed` is set.
        assert not forgotten.wait(timeout=0.2), "_forget_session ran while the lock was held"

        proceed.set()
        t1.join(timeout=5)
        t2.join(timeout=5)

    assert forgotten.is_set()
    # forget ran only after initialize finished, so it undid the freshly-set state.
    assert mcp._state == {"initialized": False, "session_id": None}


def test_jsonrpc_error_object_raises():
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            lambda req: _rpc(req["id"], error={"code": -32602, "message": "bad"}),
        ]
    )
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        pytest.raises(mcp.TradingViewMCPError, match="-32602"),
    ):
        mcp.call_tool("x")


def test_is_error_result_raises_tool_error():
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            _answer({"isError": True, "content": [{"type": "text", "text": "symbol not found"}]}),
        ]
    )
    with (
        patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server),
        pytest.raises(mcp.TradingViewToolError, match="symbol not found"),
    ):
        mcp.call_tool("x")


def test_multiple_text_blocks_decode_to_a_list():
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            _answer(
                {
                    "content": [
                        {"type": "text", "text": '{"a": 1}'},
                        {"type": "text", "text": "plain"},
                    ]
                }
            ),
        ]
    )
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.call_tool("x") == [{"a": 1}, "plain"]


def test_list_tools_follows_pagination():
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            _answer({"tools": [{"name": "a"}], "nextCursor": "c2"}),
            _answer({"tools": [{"name": "b"}]}),
        ]
    )
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert [t["name"] for t in mcp.list_tools()] == ["a", "b"]
    assert server.requests[-1]["params"] == {"cursor": "c2"}


def test_probe_reports_tool_count_and_never_raises():
    server = _Server(
        [
            lambda req: _rpc(req["id"], {}),
            httpx.Response(202),
            _answer({"tools": [{"name": "a"}, {"name": "b"}]}),
        ]
    )
    with patch("apps.market.services.tradingview_mcp.httpx.post", side_effect=server):
        assert mcp.probe() == {"ok": True, "message": "Connected — 2 tools available."}
    with patch("apps.market.services.tradingview_mcp.oauth.ensure_fresh_token", return_value=None):
        assert mcp.probe()["ok"] is False


def test_mock_mode_serves_canned_catalogue_and_results():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        names = {t["name"] for t in mcp.list_tools()}
        bars = mcp.call_tool("get_ohlcv", {"symbol": "NASDAQ:AAPL", "count": 5})
    assert {"search_symbols", "get_ohlcv", "get_news", "create_alert"} <= names
    assert len(bars["bars"]) == 5 and {"t", "o", "h", "l", "c", "v"} <= set(bars["bars"][0])
