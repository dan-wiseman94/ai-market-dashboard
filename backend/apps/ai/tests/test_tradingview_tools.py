"""TradingView tools bridged into the AI Toolset: allowlist, tv_ prefix, gating, dispatch."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.ai.tools import tradingview as bridge
from apps.ai.tools.registry import default_toolset, request_toolset

LIVE = [
    {
        "name": "get_ohlcv",
        "description": "Bars.",
        "inputSchema": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
    {
        "name": "get_screener_columns",
        "description": "Columns.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_alert",
        "description": "Write!",
        "inputSchema": {"type": "object", "properties": {"symbol": {"type": "string"}}},
    },
    {"name": "brand_new_beta_tool", "description": "?", "inputSchema": {"type": "object"}},
    {"name": "search_symbols", "description": "Search."},
]


def _enabled(value: bool):
    class _RC:
        tradingview_tools_enabled = value

    return patch("apps.core.runtime_config.runtime_config", return_value=_RC())


def test_allowlist_has_25_read_only_names() -> None:
    assert len(bridge.TRADINGVIEW_TOOL_ALLOWLIST) == 25
    assert not any(
        n.startswith(("create_", "update_", "delete_", "add_", "remove_", "stop_", "restart_"))
        for n in bridge.TRADINGVIEW_TOOL_ALLOWLIST
    )


@pytest.mark.django_db
def test_toolset_is_allowlist_intersected_with_live_list_and_prefixed() -> None:
    with (
        _enabled(True),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview_mcp.list_tools", return_value=LIVE),
    ):
        ts = bridge.tradingview_toolset()
    assert set(ts.specs) == {"tv_get_ohlcv", "tv_get_screener_columns", "tv_search_symbols"}
    ohlcv = ts.specs["tv_get_ohlcv"]
    assert ohlcv.description.startswith("TradingView: Bars.")
    assert "EXCHANGE:TICKER" in ohlcv.description and "tv_search_symbols" in ohlcv.description
    assert "EXCHANGE:TICKER" not in ts.specs["tv_get_screener_columns"].description
    assert ohlcv.input_schema["required"] == ["symbol"]
    assert ts.specs["tv_search_symbols"].input_schema == {"type": "object", "properties": {}}


@pytest.mark.django_db
@pytest.mark.parametrize(("enabled", "connected"), [(False, True), (True, False), (False, False)])
def test_toolset_empty_unless_enabled_and_connected(enabled, connected) -> None:
    with (
        _enabled(enabled),
        patch("apps.market.services.tradingview.is_connected", return_value=connected),
        patch("apps.market.services.tradingview_mcp.list_tools", return_value=LIVE) as lt,
    ):
        assert bridge.tradingview_toolset().specs == {}
    lt.assert_not_called()


@pytest.mark.django_db
def test_toolset_empty_when_list_tools_fails() -> None:
    with (
        _enabled(True),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview_mcp.list_tools", side_effect=RuntimeError("down")),
    ):
        assert bridge.tradingview_toolset().specs == {}


def test_resolve_dynamic_only_allowlisted_tv_names() -> None:
    assert bridge.resolve_dynamic("get_quote") is None
    assert bridge.resolve_dynamic("tv_create_alert") is None
    spec = bridge.resolve_dynamic("tv_get_news")
    assert spec is not None and spec.name == "tv_get_news"


def test_tv_spec_runs_call_tool_with_kwargs() -> None:
    spec = bridge.resolve_dynamic("tv_get_ohlcv")
    with patch("apps.market.services.tradingview_mcp.call_tool", return_value={"bars": []}) as c:
        assert spec.fn(symbol="NASDAQ:AAPL", interval="1D") == {"bars": []}
    c.assert_called_once_with("get_ohlcv", {"symbol": "NASDAQ:AAPL", "interval": "1D"})


def test_default_toolset_dispatches_tv_names_without_io() -> None:
    ts = default_toolset()
    with patch("apps.market.services.tradingview_mcp.call_tool", return_value="ok") as c:
        assert ts.run("tv_get_news", {"symbol": "NASDAQ:AAPL"}) == {"ok": True, "result": "ok"}
        assert ts.run("tv_create_alert", {"symbol": "x", "price": 1})["ok"] is False
    c.assert_called_once()


@pytest.mark.django_db
def test_request_toolset_merges_tradingview_specs() -> None:
    with (
        _enabled(True),
        patch("apps.market.services.tradingview.is_connected", return_value=True),
        patch("apps.market.services.tradingview_mcp.list_tools", return_value=LIVE),
    ):
        names = set(request_toolset().specs)
    assert {"get_quote", "fetch_ohlc", "tv_get_ohlcv"} <= names
