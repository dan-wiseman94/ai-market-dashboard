"""TradingView MCP tools bridged into the AI Toolset (read-only allowlist).

Two halves, split on purpose:
- ``tradingview_toolset()`` does I/O (runtime_config → ORM, cached tools/list → Redis /
  HTTP) and is only called on the SYNC request-assembly path
  (``registry.request_toolset``), where the tool *schemas* go on the RunRequest.
- ``resolve_dynamic(name)`` is pure. ``default_toolset()`` registers it, so the
  providers' async streaming loops can dispatch a ``tv_*`` call without touching the ORM
  or the network at lookup time (execution runs under sync_to_async, where I/O is fine).

Every bridged tool is ``tv_<name>`` so provenance shows in ToolCall rows and the thread
UI and native names never collide. Write tools are never exposed — the allowlist is the
only source of exposable names; new beta tools stay out until added here.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from django.core.exceptions import SynchronousOnlyOperation

from apps.ai.tools import Toolset, ToolSpec

log = logging.getLogger(__name__)

TV_PREFIX = "tv_"
MAX_RESULT_CHARS = 32_000
_MAX_DESCRIPTION_CHARS = 1_000
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
TRADINGVIEW_TOOL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "list_watchlists",
        "get_watchlist",
        "get_active_watchlist",
        "get_ohlcv",
        "get_economic_data",
        "get_economic_symbols",
        "search_symbols",
        "run_screener",
        "get_symbol_data",
        "get_symbol_data_batch",
        "get_screener_columns",
        "get_technicals_rating",
        "get_news",
        "get_news_story",
        "get_forecasts",
        "get_financials",
        "get_financial_history",
        "get_documents",
        "get_document_view",
        "get_earnings_calendar",
        "get_economic_calendar",
        "get_dividends_calendar",
        "list_alerts",
        "get_alerts",
        "get_alerts_log",
    }
)
_SYMBOL_NOTE = (
    " Symbols are EXCHANGE:TICKER (e.g. NASDAQ:AAPL, CME_MINI:ES1!, TVC:VIX); "
    "use tv_search_symbols to resolve a bare ticker."
)


def _cap_result(result: Any) -> Any:
    """Cap a tool result at ``MAX_RESULT_CHARS`` of serialized JSON so a wide screener/
    OHLCV pull can't blow the request's token budget or a downstream log line."""
    text = json.dumps(result, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return result
    return {
        "truncated": True,
        "chars": len(text),
        "preview": text[:MAX_RESULT_CHARS],
        "note": (
            "TradingView result truncated to 32,000 chars; narrow the request "
            "(fewer bars/rows, a specific symbol)."
        ),
    }


def _clean_description(text: str) -> str:
    """Strip ASCII control characters and cap length — a hostile/malformed upstream
    description must not blow up the provider's tools= payload."""
    return _CONTROL_CHAR_RE.sub("", text)[:_MAX_DESCRIPTION_CHARS]


def _runner(tool_name: str) -> Callable[..., Any]:
    def run(**kwargs: Any) -> Any:
        from apps.core.runtime_config import runtime_config
        from apps.market.services import tradingview, tradingview_mcp

        if not runtime_config().tradingview_tools_enabled:
            raise RuntimeError("TradingView tools are disabled in Settings → Connections")
        if not tradingview.is_connected():
            raise RuntimeError("TradingView is not connected")
        result = tradingview_mcp.call_tool(tool_name, kwargs)
        return _cap_result(result)

    run.__name__ = f"{TV_PREFIX}{tool_name}"
    return run


def _spec_from(tool: dict) -> ToolSpec | None:
    name = str(tool.get("name") or "")
    if name not in TRADINGVIEW_TOOL_ALLOWLIST:
        return None
    raw_schema = tool.get("inputSchema")
    schema = dict(raw_schema) if isinstance(raw_schema, dict) else {}
    # Normalize, don't just setdefault — the live server can send "properties": null (or
    # any non-dict) or omit "type"; a malformed schema reaching anthropic_tools()/
    # openai_tools() can make the provider reject the whole tools= payload for the turn.
    if schema.get("type") != "object":
        schema["type"] = "object"
    props = schema.get("properties")
    if not isinstance(props, dict):
        props = {}
        schema["properties"] = props
    description = _clean_description(f"TradingView: {tool.get('description') or name}")
    if "symbol" in props or "symbols" in props:
        description += _SYMBOL_NOTE
    return ToolSpec(
        name=f"{TV_PREFIX}{name}", description=description, input_schema=schema, fn=_runner(name)
    )


def tradingview_toolset() -> Toolset:
    """Allowlisted ``tv_*`` specs when the toggle is on AND TradingView is connected;
    otherwise (or on any transport error) an empty toolset. Sync path only."""
    toolset = Toolset()
    try:
        from apps.core.runtime_config import runtime_config
        from apps.market.services import tradingview, tradingview_mcp

        if not runtime_config().tradingview_tools_enabled or not tradingview.is_connected():
            return toolset
        for tool in tradingview_mcp.list_tools():
            # Isolate one bad entry so it can't take down the whole toolset for the turn.
            try:
                spec = _spec_from(tool)
            except Exception as exc:
                entry_name = tool.get("name") if isinstance(tool, dict) else "<unknown>"
                log.warning("TradingView tool entry skipped: %s (%s)", entry_name, exc)
                continue
            if spec is not None:
                toolset.register(spec)
    except SynchronousOnlyOperation:
        # Misuse from an async context (calling this off the sync request-assembly
        # path) must fail loudly, not degrade to an empty toolset.
        raise
    except Exception:
        log.warning("TradingView tools unavailable for this run", exc_info=True)
        return Toolset()
    return toolset


def resolve_dynamic(name: str) -> ToolSpec | None:
    """Pure resolver for ``default_toolset()``: ``tv_<allowlisted>`` → a runnable spec."""
    if not name.startswith(TV_PREFIX):
        return None
    bare = name[len(TV_PREFIX) :]
    if bare not in TRADINGVIEW_TOOL_ALLOWLIST:
        return None
    return ToolSpec(
        name=name,
        description=f"TradingView: {bare}",
        input_schema={"type": "object"},
        fn=_runner(bare),
    )
