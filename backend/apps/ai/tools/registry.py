"""Default Toolset wiring existing market services as tools for Claude."""

from __future__ import annotations

from apps.ai.tools import Toolset, ToolSpec
from apps.market.services.chain import fetch_chain as fetch_chain_svc
from apps.market.services.indicator import compute as compute_ind_svc
from apps.market.services.news import fetch_news as fetch_news_svc
from apps.market.services.ohlc import fetch_ohlc as fetch_ohlc_svc
from apps.market.services.quotes import fetch_quotes


def _get_quote(*, ticker: str) -> dict:
    return fetch_quotes([ticker])


def _fetch_ohlc(*, ticker: str, timeframe: str, bars: int = 60) -> list[dict]:
    return fetch_ohlc_svc(ticker, timeframe=timeframe, bars=bars)


def _search_news(*, tickers: list[str], lookback_hours: int = 24, limit: int = 10) -> list[dict]:
    return fetch_news_svc(tickers, lookback_hours=lookback_hours, limit=limit)


def _get_option_chain(*, ticker: str, strikes_around_atm: int = 10) -> dict:
    return fetch_chain_svc(ticker, strikes_around_atm=strikes_around_atm)


def _compute_indicator(
    *,
    ticker: str,
    indicator: str,
    period: int,
    timeframe: str = "1d",
    bars: int = 100,
) -> float | None:
    raw = fetch_ohlc_svc(ticker, timeframe=timeframe, bars=bars)
    if indicator.upper() == "ATR":
        return compute_ind_svc("ATR", raw, period=period)
    closes = [float(b["close"]) for b in raw if b.get("close") is not None]
    return compute_ind_svc(indicator, closes, period=period)


def _recall(*, query: str, k: int = 5) -> list[dict]:
    from apps.recall.services.search import search

    return search(query, k=k)


def default_toolset() -> Toolset:
    ts = Toolset()
    ts.register(
        ToolSpec(
            name="get_quote",
            description="Get the latest quote for a single ticker. "
            "Returns last/bid/ask/volume/high/low/pct_change.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Stock symbol, e.g. AAPL"}
                },
                "required": ["ticker"],
            },
            fn=_get_quote,
        )
    )
    ts.register(
        ToolSpec(
            name="fetch_ohlc",
            description="Fetch OHLC bars for a ticker. timeframe ∈ "
            "{1m,5m,15m,1h,1d}. Use to read price action.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "timeframe": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "1d"]},
                    "bars": {"type": "integer", "minimum": 5, "maximum": 500, "default": 60},
                },
                "required": ["ticker", "timeframe"],
            },
            fn=_fetch_ohlc,
        )
    )
    ts.register(
        ToolSpec(
            name="search_news",
            description="Fetch recent news headlines for one or more tickers. "
            "Returns list with headline, summary, source, url, datetime.",
            input_schema={
                "type": "object",
                "properties": {
                    "tickers": {"type": "array", "items": {"type": "string"}},
                    "lookback_hours": {
                        "type": "integer",
                        "default": 24,
                        "minimum": 1,
                        "maximum": 168,
                    },
                    "limit": {"type": "integer", "default": 10, "minimum": 1, "maximum": 30},
                },
                "required": ["tickers"],
            },
            fn=_search_news,
        )
    )
    ts.register(
        ToolSpec(
            name="get_option_chain",
            description="Fetch an option chain for a ticker. Returns expiries "
            "with calls/puts arrays incl. strike/bid/ask/delta/IV.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "strikes_around_atm": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 2,
                        "maximum": 30,
                    },
                },
                "required": ["ticker"],
            },
            fn=_get_option_chain,
        )
    )
    ts.register(
        ToolSpec(
            name="compute_indicator",
            description="Compute a technical indicator. indicator ∈ {SMA,EMA,RSI,ATR}. "
            "Uses fetched OHLC internally.",
            input_schema={
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "indicator": {"type": "string", "enum": ["SMA", "EMA", "RSI", "ATR"]},
                    "period": {"type": "integer", "minimum": 2, "maximum": 200},
                    "timeframe": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "1h", "1d"],
                        "default": "1d",
                    },
                    "bars": {"type": "integer", "default": 100, "minimum": 10, "maximum": 500},
                },
                "required": ["ticker", "indicator", "period"],
            },
            fn=_compute_indicator,
        )
    )
    ts.register(
        ToolSpec(
            name="recall",
            description=(
                "Search your own past observations, theses, snapshots, and notes by meaning. "
                "Returns top matches with kind, snippet, and link."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
                "required": ["query"],
            },
            fn=_recall,
        )
    )
    return ts
