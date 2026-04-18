"""Default registry binds the five tools to existing market services."""
from __future__ import annotations

from unittest.mock import patch

from apps.ai.tools.registry import default_toolset


def test_default_toolset_registers_five_tools() -> None:
    ts = default_toolset()
    names = set(ts.specs)
    assert names == {
        "get_quote", "fetch_ohlc", "search_news",
        "get_option_chain", "compute_indicator",
    }


def test_get_quote_calls_fetch_quotes() -> None:
    ts = default_toolset()
    with patch(
        "apps.ai.tools.registry.fetch_quotes",
        return_value={"AAPL": {"last": 180.0}},
    ) as m:
        res = ts.run("get_quote", {"ticker": "AAPL"})
    assert res == {"ok": True, "result": {"AAPL": {"last": 180.0}}}
    m.assert_called_once_with(["AAPL"])


def test_fetch_ohlc_threads_kwargs() -> None:
    ts = default_toolset()
    with patch("apps.ai.tools.registry.fetch_ohlc_svc", return_value=[]) as m:
        ts.run("fetch_ohlc", {"ticker": "SPY", "timeframe": "1d", "bars": 30})
    m.assert_called_once_with("SPY", timeframe="1d", bars=30)


def test_compute_indicator_uses_fetch_ohlc_closes() -> None:
    ts = default_toolset()
    bars = [{"close": float(i)} for i in range(1, 21)]
    with patch("apps.ai.tools.registry.fetch_ohlc_svc", return_value=bars):
        res = ts.run("compute_indicator", {
            "ticker": "SPY", "indicator": "SMA",
            "period": 5, "timeframe": "1d",
        })
    assert res["ok"] is True
    assert res["result"] == 18.0


def test_unknown_tool_returns_error() -> None:
    ts = default_toolset()
    res = ts.run("make_coffee", {})
    assert res == {"ok": False, "error": "Unknown tool: make_coffee"}


def test_tool_error_is_captured_not_raised() -> None:
    ts = default_toolset()
    with patch("apps.ai.tools.registry.fetch_quotes", side_effect=RuntimeError("boom")):
        res = ts.run("get_quote", {"ticker": "X"})
    assert res["ok"] is False
    assert "boom" in res["error"]


def test_anthropic_tools_shape() -> None:
    ts = default_toolset()
    tools = ts.anthropic_tools()
    assert len(tools) == 5
    first = tools[0]
    assert {"name", "description", "input_schema"} <= set(first)
