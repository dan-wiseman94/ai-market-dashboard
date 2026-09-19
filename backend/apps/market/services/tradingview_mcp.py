"""MCP client for TradingView's official server (Streamable HTTP, JSON-RPC 2.0).

Dependency-free — we need only ``initialize`` / ``notifications/initialized`` /
``tools/list`` / ``tools/call``, mirroring the hand-rolled MCP-out server in
``apps.core.mcp``. The bearer token comes from ``tradingview_oauth.ensure_fresh_token``
(lazy refresh under a Redis lock).

Responses arrive as ``application/json`` or as an SSE stream (``text/event-stream``);
both are reduced to the JSON-RPC message answering our id. A ``Mcp-Session-Id`` from
``initialize`` is echoed on later calls; a 404 means the session expired → re-initialize
once. A 401 forces one token refresh and one retry; a second 401 records the
provider_health marker (the fallback router then stops consulting TradingView).
Never logs the token.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from itertools import count
from typing import Any

import httpx
import redis
from django.conf import settings

from apps.market import cache
from apps.market.services.safe_log import safe_err
from apps.secrets import tradingview_oauth as oauth

log = logging.getLogger(__name__)

PROTOCOL_VERSION = "2025-06-18"
CLIENT_INFO = {"name": "ledger", "version": "1.0.0"}
TOOLS_CACHE_KEY = "tradingview:mcp:tools"
TOOLS_CACHE_TTL_SECONDS = 3600
_TIMEOUT = 20.0
_MAX_PAGES = 20

_state: dict[str, Any] = {"initialized": False, "session_id": None, "last_id": 0}
_session_lock = threading.Lock()
_ids = count(1)


class TradingViewMCPError(RuntimeError):
    """Transport / protocol failure (HTTP error, malformed body, JSON-RPC error)."""


class TradingViewNotConnected(TradingViewMCPError):
    """No usable token: not connected, or the refresh/access token was rejected."""


class TradingViewRateLimited(TradingViewMCPError):
    """HTTP 429 — the ~100 calls/min per-user budget is spent. Not retried."""


class TradingViewToolError(TradingViewMCPError):
    """``tools/call`` answered ``isError`` — the tool ran but reported failure."""


class _Unauthorized(Exception):
    pass


class _SessionExpired(Exception):
    pass


def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.REDIS_URL)


def _last_id() -> int:
    return int(_state["last_id"])


def _next_id() -> int:
    rpc_id = next(_ids)
    _state["last_id"] = rpc_id
    return rpc_id


def _forget_session() -> None:
    _state["initialized"] = False
    _state["session_id"] = None


def reset_state() -> None:
    """Forget the process-local session and the cached tool list (disconnect / tests)."""
    _forget_session()
    try:
        _redis().delete(TOOLS_CACHE_KEY)
    except Exception:
        log.debug("Could not clear the TradingView tools cache", exc_info=True)


# --- wire -------------------------------------------------------------------------------


def _headers(token: str) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": PROTOCOL_VERSION,
    }
    if _state["session_id"]:
        headers["Mcp-Session-Id"] = str(_state["session_id"])
    return headers


def _post(message: dict, token: str) -> httpx.Response:
    try:
        return httpx.post(
            settings.TRADINGVIEW_MCP_URL, json=message, headers=_headers(token), timeout=_TIMEOUT
        )
    except httpx.HTTPError as exc:
        raise TradingViewMCPError(f"TradingView MCP unreachable: {safe_err(exc)}") from exc


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code == 401:
        raise _Unauthorized
    if resp.status_code == 404:
        raise _SessionExpired
    if resp.status_code == 429:
        raise TradingViewRateLimited("TradingView MCP rate limit reached (HTTP 429)")
    if resp.status_code >= 400:
        raise TradingViewMCPError(f"TradingView MCP returned HTTP {resp.status_code}")


def _parse_sse(text: str, rpc_id: int) -> dict | None:
    """The JSON-RPC message with ``id == rpc_id`` from an SSE body. Each event's
    ``data:`` lines are joined; server-initiated requests/notifications are ignored."""
    data_lines: list[str] = []
    for raw in [*text.splitlines(), ""]:
        line = raw.rstrip("\r")
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
            continue
        if line == "" and data_lines:
            try:
                msg = json.loads("\n".join(data_lines))
            except ValueError:
                msg = None
            data_lines = []
            if isinstance(msg, dict) and msg.get("id") == rpc_id:
                return msg
    return None


def _parse_response(resp: httpx.Response, rpc_id: int) -> dict:
    ctype = resp.headers.get("content-type", "")
    if ctype.startswith("text/event-stream"):
        msg = _parse_sse(resp.text, rpc_id)
    else:
        try:
            body = resp.json()
        except ValueError as exc:
            raise TradingViewMCPError("TradingView MCP returned a non-JSON body") from exc
        msg = body if isinstance(body, dict) else None
    if msg is None:
        raise TradingViewMCPError("TradingView MCP response did not answer the request")
    if msg.get("error"):
        err = msg["error"] if isinstance(msg["error"], dict) else {}
        raise TradingViewMCPError(f"JSON-RPC error {err.get('code')}: {err.get('message')}")
    return msg


def _initialize(token: str) -> None:
    rpc_id = _next_id()
    resp = _post(
        {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": CLIENT_INFO,
            },
        },
        token,
    )
    _raise_for_status(resp)
    _parse_response(resp, rpc_id)
    _state["session_id"] = resp.headers.get("Mcp-Session-Id") or None
    ack = _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, token)
    _raise_for_status(ack)
    _state["initialized"] = True


def _mark_rejected() -> None:
    from apps.core import provider_health

    provider_health.mark_auth_error("tradingview", oauth.REJECTED_MESSAGE)


def _send(method: str, params: dict, token: str) -> dict:
    with _session_lock:
        if not _state["initialized"]:
            _initialize(token)
    rpc_id = _next_id()
    resp = _post({"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}, token)
    _raise_for_status(resp)
    result = _parse_response(resp, rpc_id).get("result")
    return result if isinstance(result, dict) else {}


def _request(method: str, params: dict | None = None) -> dict:
    """One JSON-RPC request with session bootstrap, 404 re-init and 401 refresh-retry."""
    token = oauth.ensure_fresh_token()
    if token is None:
        raise TradingViewNotConnected("TradingView is not connected")
    refreshed = reinitialized = False
    while True:
        try:
            return _send(method, params or {}, token)
        except _Unauthorized:
            if refreshed:
                _mark_rejected()
                raise TradingViewNotConnected("TradingView rejected the access token") from None
            refreshed = True
            # Keep the session: a 401 is about the token, not the session id. If the
            # server also dropped the session it answers 404 next, which re-inits.
            token = oauth.ensure_fresh_token(force=True)
            if token is None:
                raise TradingViewNotConnected("TradingView token refresh failed") from None
        except _SessionExpired:
            if reinitialized:
                raise TradingViewMCPError(
                    "TradingView MCP session could not be re-established"
                ) from None
            reinitialized = True
            _forget_session()


# --- results ----------------------------------------------------------------------------


def _text_of(result: dict) -> str:
    blocks = result.get("content") or []
    return "\n".join(
        str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text"
    )


def _decode_tool_result(result: dict) -> Any:
    if result.get("isError"):
        raise TradingViewToolError(_text_of(result)[:500] or "tool reported an error")
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    decoded: list[Any] = []
    for block in result.get("content") or []:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = str(block.get("text", ""))
        try:
            decoded.append(json.loads(text))
        except ValueError:
            decoded.append(text)
    if not decoded:
        return None
    return decoded[0] if len(decoded) == 1 else decoded


# --- public API --------------------------------------------------------------------------


def _fetch_all_tools() -> list[dict]:
    tools: list[dict] = []
    cursor: str | None = None
    for _ in range(_MAX_PAGES):
        result = _request("tools/list", {"cursor": cursor} if cursor else {})
        tools.extend(t for t in result.get("tools") or [] if isinstance(t, dict))
        cursor = result.get("nextCursor") or None
        if not cursor:
            break
    return tools


def list_tools(*, use_cache: bool = True) -> list[dict]:
    """The server's tool schemas (``name``/``description``/``inputSchema``), Redis-cached 1h."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return [dict(t) for t in MOCK_TOOLS]
    if not use_cache:
        return _fetch_all_tools()
    return cache.get_or_fetch(
        TOOLS_CACHE_KEY, ttl_seconds=TOOLS_CACHE_TTL_SECONDS, fetcher=_fetch_all_tools
    )


def call_tool(name: str, arguments: dict | None = None) -> Any:
    """Run one tool. Returns ``structuredContent`` when present, else the JSON-decoded
    text block(s). Raises TradingViewToolError on ``isError``."""
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return mock_call(name, arguments or {})
    return _decode_tool_result(_request("tools/call", {"name": name, "arguments": arguments or {}}))


def probe() -> dict:
    """Settings → "Test connection": ``{ok, message}``; never raises."""
    try:
        tools = list_tools(use_cache=False)
    except TradingViewNotConnected:
        return {"ok": False, "message": "Not connected — connect TradingView first."}
    except TradingViewMCPError as exc:
        return {"ok": False, "message": f"Couldn't reach TradingView MCP ({exc})."}
    except Exception as exc:
        log.warning("tradingview.probe.failed: %s", safe_err(exc))
        return {"ok": False, "message": "Couldn't reach TradingView MCP."}
    return {"ok": True, "message": f"Connected — {len(tools)} tools available."}


# --- MOCK_EXTERNAL catalogue -------------------------------------------------------------

_MOCK_NOW = 1_760_000_000  # fixed epoch so fixtures are stable
_DAY = 86_400


def _schema(props: dict, required: list[str] | None = None) -> dict:
    schema: dict = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


MOCK_TOOLS: list[dict] = [
    {
        "name": "search_symbols",
        "description": "Search symbols.",
        "inputSchema": _schema(
            {"query": {"type": "string"}, "type_filter": {"type": "string"}}, ["query"]
        ),
    },
    {
        "name": "get_ohlcv",
        "description": "OHLCV bars.",
        "inputSchema": _schema(
            {
                "symbol": {"type": "string"},
                "interval": {"type": "string"},
                "count": {"type": "integer"},
                "summary": {"type": "boolean"},
            },
            ["symbol"],
        ),
    },
    {
        "name": "get_symbol_data_batch",
        "description": "Screener columns for symbols.",
        "inputSchema": _schema(
            {
                "symbols": {"type": "array", "items": {"type": "string"}},
                "columns": {"type": "array", "items": {"type": "string"}},
            },
            ["symbols"],
        ),
    },
    {
        "name": "get_news",
        "description": "Headlines for a symbol.",
        "inputSchema": _schema(
            {"symbol": {"type": "string"}, "limit": {"type": "integer"}}, ["symbol"]
        ),
    },
    {
        "name": "get_earnings_calendar",
        "description": "Earnings dates.",
        "inputSchema": _schema(
            {"symbols": {"type": "array", "items": {"type": "string"}}}, ["symbols"]
        ),
    },
    {
        "name": "get_economic_calendar",
        "description": "Macro events.",
        "inputSchema": _schema(
            {
                "countries": {"type": "array", "items": {"type": "string"}},
                "from_date": {"type": "string"},
                "to_date": {"type": "string"},
            }
        ),
    },
    {
        "name": "create_alert",
        "description": "Create a price alert (write).",
        "inputSchema": _schema(
            {"symbol": {"type": "string"}, "price": {"type": "number"}}, ["symbol", "price"]
        ),
    },
]


def _mock_search(a: dict) -> Any:
    q = str(a.get("query") or "AAPL").upper()
    return {
        "symbols": [{"symbol": f"NASDAQ:{q}", "ticker": q, "exchange": "NASDAQ", "type": "stock"}]
    }


def _mock_ohlcv(a: dict) -> Any:
    n = max(1, min(int(a.get("count") or 30), 30))
    bars = [
        {
            "t": _MOCK_NOW - (n - i) * _DAY,
            "o": 150.0,
            "h": 152.0,
            "l": 148.0,
            "c": 150.0 + (i % 3),
            "v": 1_000_000 + i,
        }
        for i in range(n)
    ]
    return {"symbol": a.get("symbol"), "bars": bars}


def _mock_batch(a: dict) -> Any:
    rows = [
        {
            "symbol": s,
            "close": 150.0,
            "change": 1.23,
            "volume": 1_000_000,
            "high": 152.0,
            "low": 148.0,
        }
        for s in a.get("symbols") or []
    ]
    return {"data": rows}


def _mock_news(a: dict) -> Any:
    sym = str(a.get("symbol") or "NASDAQ:AAPL")
    item = {
        "id": f"tv-{sym}-1",
        "title": f"Mock TradingView headline for {sym}",
        "published": _MOCK_NOW,
        "provider": "MockWire",
        "storyPath": "/news/mock-1/",
        "link": "",
        "relatedSymbols": [{"symbol": sym}],
    }
    return {"items": [item], "has_more": False}


def _mock_earnings(a: dict) -> Any:
    return {
        "events": [
            {
                "symbol": s,
                "date": "2026-10-28",
                "time": "amc",
                "eps_estimate": 1.5,
                "revenue_estimate": 9.0e10,
            }
            for s in a.get("symbols") or []
        ]
    }


def _mock_macro(_a: dict) -> Any:
    return {
        "events": [
            {
                "title": "Consumer Price Index (MoM)",
                "country": "US",
                "importance": "high",
                "date": "2026-10-14T12:30:00Z",
                "forecast": 0.3,
                "previous": 0.2,
                "actual": None,
            }
        ]
    }


_MOCK_RESULTS: dict[str, Callable[[dict], Any]] = {
    "search_symbols": _mock_search,
    "get_ohlcv": _mock_ohlcv,
    "get_symbol_data_batch": _mock_batch,
    "get_news": _mock_news,
    "get_earnings_calendar": _mock_earnings,
    "get_economic_calendar": _mock_macro,
}


def mock_call(name: str, arguments: dict) -> Any:
    """Deterministic canned results for MOCK_EXTERNAL (shapes per the TradingView docs;
    the normalizers in ``tradingview.py`` are lenient about key spellings)."""
    handler = _MOCK_RESULTS.get(name)
    return handler(arguments) if handler else {"ok": True}
