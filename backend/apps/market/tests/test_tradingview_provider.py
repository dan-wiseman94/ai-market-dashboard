"""TradingView as a market-data provider: symbol mapping + contract normalizers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.market.models import NewsItem, OHLCBar
from apps.market.services import tradingview as tv

_PASSTHRU = {"side_effect": lambda key, *, ttl_seconds, fetcher: fetcher()}


@pytest.fixture(autouse=True)
def _no_cache():
    with patch("apps.market.services.tradingview.cache.get_or_fetch", **_PASSTHRU):
        yield


def _tools(table: dict):
    def _call(name, arguments=None):
        handler = table[name]
        return handler(arguments or {}) if callable(handler) else handler

    return patch("apps.market.services.tradingview.mcp.call_tool", side_effect=_call)


@pytest.mark.django_db
def test_is_connected_requires_token_and_no_marker():
    with patch("apps.market.services.tradingview.load_token", return_value=None):
        assert tv.is_connected() is False
    with (
        patch("apps.market.services.tradingview.load_token", return_value={"access_token": "a"}),
        patch("apps.core.provider_health.auth_error", return_value=None),
    ):
        assert tv.is_connected() is True
    with (
        patch("apps.market.services.tradingview.load_token", return_value={"access_token": "a"}),
        patch("apps.core.provider_health.auth_error", return_value="rejected"),
    ):
        assert tv.is_connected() is False


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("$VIX", "TVC:VIX"),
        ("VIX", "TVC:VIX"),
        ("SPX", "SP:SPX"),
        ("/ES", "CME_MINI:ES1!"),
        ("ES", "CME_MINI:ES1!"),
        ("/VX", "CFE:VX1!"),
        ("$ADVN", None),
        ("", None),
    ],
)
def test_symbol_table(ticker, expected):
    with patch("apps.market.services.tradingview.mcp.call_tool") as c:
        assert tv.to_tv_symbol(ticker) == expected
    c.assert_not_called()


def test_equity_resolves_via_search_preferring_us_exchange():
    hits = {
        "symbols": [
            {"symbol": "LSE:AAPL", "ticker": "AAPL", "exchange": "LSE"},
            {"symbol": "NASDAQ:AAPL", "ticker": "AAPL", "exchange": "NASDAQ"},
        ]
    }
    with _tools({"search_symbols": hits}) as c:
        assert tv.to_tv_symbol("aapl") == "NASDAQ:AAPL"
    assert c.call_args.args == ("search_symbols", {"query": "AAPL", "type_filter": "stock"})


def test_equity_retries_as_etf_then_gives_up():
    calls = []

    def _search(a):
        calls.append(a["type_filter"])
        return {
            "symbols": [{"symbol": "AMEX:SPY", "ticker": "SPY", "exchange": "AMEX"}]
            if a["type_filter"] == "etf"
            else []
        }

    with _tools({"search_symbols": _search}):
        assert tv.to_tv_symbol("SPY") == "AMEX:SPY"
    assert calls == ["stock", "etf"]
    with _tools({"search_symbols": {"symbols": []}}):
        assert tv.to_tv_symbol("ZZZZ") is None


def test_symbol_resolution_failure_returns_none():
    with _tools({"search_symbols": lambda a: (_ for _ in ()).throw(RuntimeError("boom"))}):
        assert tv.to_tv_symbol("AAPL") is None


@pytest.mark.django_db
def test_fetch_bars_normalizes_sorts_and_persists():
    raw = {
        "bars": [
            {"t": 1_760_086_400, "o": 2, "h": 3, "l": 1, "c": 2.5, "v": 20},
            {"t": 1_760_000_000, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10},
            {"t": None},
        ]
    }
    with _tools(
        {
            "search_symbols": {
                "symbols": [{"symbol": "NASDAQ:AAPL", "ticker": "AAPL", "exchange": "NASDAQ"}]
            },
            "get_ohlcv": raw,
        }
    ) as c:
        bars = tv.fetch_bars("AAPL", timeframe="1d", limit=60)
    assert c.call_args_list[-1].args == (
        "get_ohlcv",
        {"symbol": "NASDAQ:AAPL", "interval": "1D", "count": 60, "summary": False},
    )
    assert [b["close"] for b in bars] == [1.5, 2.5]
    assert bars[0]["ts"] == "2025-10-09T08:53:20+00:00"
    assert OHLCBar.objects.filter(ticker="AAPL", timeframe="1d").count() == 2


@pytest.mark.parametrize(
    ("tf", "interval"), [("1m", "1"), ("5m", "5"), ("15m", "15"), ("1h", "60"), ("1d", "1D")]
)
@pytest.mark.django_db
def test_fetch_bars_interval_map(tf, interval):
    with (
        _tools({"get_ohlcv": {"bars": []}}) as c,
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="SP:SPX"),
    ):
        tv.fetch_bars("$SPX", timeframe=tf, limit=5)
    assert c.call_args.args[1]["interval"] == interval


@pytest.mark.django_db
def test_fetch_bars_unmappable_or_failing_returns_empty():
    assert tv.fetch_bars("$ADVN", timeframe="1d") == []
    with (
        _tools({"get_ohlcv": lambda a: (_ for _ in ()).throw(RuntimeError("x"))}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="SP:SPX"),
    ):
        assert tv.fetch_bars("$SPX", timeframe="1d") == []


def test_fetch_quotes_maps_batch_rows_to_contract():
    raw = {
        "data": [
            {
                "symbol": "NASDAQ:AAPL",
                "close": "171.3",
                "change": -0.5,
                "volume": "1234.0",
                "high": 172,
                "low": 169,
            }
        ]
    }
    with (
        _tools({"get_symbol_data_batch": raw}) as c,
        patch(
            "apps.market.services.tradingview.to_tv_symbol",
            side_effect=lambda t: {"AAPL": "NASDAQ:AAPL", "$ADVN": None}[t],
        ),
    ):
        out = tv.fetch_quotes(["AAPL", "$ADVN"])
    assert c.call_args.args[1]["symbols"] == ["NASDAQ:AAPL"]
    assert out == {
        "AAPL": {
            "last": 171.3,
            "bid": None,
            "ask": None,
            "volume": 1234,
            "high": 172.0,
            "low": 169.0,
            "pct_change": -0.5,
        }
    }


def test_fetch_quotes_accepts_scanner_style_rows():
    raw = {
        "columns": ["close", "change", "volume", "high", "low"],
        "data": [{"s": "NASDAQ:AAPL", "d": [1, 2, 3, 4, 5]}],
    }
    with (
        _tools({"get_symbol_data_batch": raw}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"),
    ):
        assert tv.fetch_quotes(["AAPL"])["AAPL"]["last"] == 1.0


def test_fetch_quotes_failure_returns_empty():
    with (
        _tools({"get_symbol_data_batch": lambda a: (_ for _ in ()).throw(RuntimeError("x"))}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"),
    ):
        assert tv.fetch_quotes(["AAPL"]) == {}


@pytest.mark.django_db
def test_fetch_news_normalizes_dedups_and_upserts():
    item = {
        "id": 77,
        "title": "Apple beats",
        "published": 1_760_000_000,
        "provider": "Reuters",
        "storyPath": "/news/apple-beats/",
        "link": "",
    }
    with (
        _tools({"get_news": {"items": [item, item]}}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"),
    ):
        items = tv.fetch_news(["AAPL"], limit=5)
    assert len(items) == 1
    it = items[0]
    assert (
        it["headline"] == "Apple beats"
        and it["source"] == "Reuters"
        and it["datetime"] == 1_760_000_000
    )
    assert it["url"] == "https://www.tradingview.com/news/apple-beats/"
    assert it["ticker"] == "AAPL" and it["tickers"] == ["AAPL"] and it["related"] == "AAPL"
    assert NewsItem.objects.get(provider="tradingview", external_id="77").headline == "Apple beats"


@pytest.mark.django_db
def test_fetch_news_failure_per_ticker_is_skipped():
    with (
        _tools({"get_news": lambda a: (_ for _ in ()).throw(RuntimeError("x"))}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"),
    ):
        assert tv.fetch_news(["AAPL"]) == []


@pytest.mark.django_db
def test_fetch_news_skips_item_with_unparseable_timestamp():
    bad = {"id": 1, "title": "Bad ts", "published": 10**20, "provider": "X", "link": "https://x"}
    good = {
        "id": 2,
        "title": "Good",
        "published": 1_760_000_000,
        "provider": "Y",
        "link": "https://y",
    }
    with (
        _tools({"get_news": {"items": [bad, good]}}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"),
    ):
        items = tv.fetch_news(["AAPL"], limit=5)
    assert len(items) == 1
    assert items[0]["headline"] == "Good"


@pytest.mark.django_db
def test_fetch_news_persistence_failure_still_returns_items():
    item = {
        "id": 3,
        "title": "Persist fail",
        "published": 1_760_000_000,
        "provider": "Z",
        "link": "https://z",
    }
    with (
        _tools({"get_news": {"items": [item]}}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:AAPL"),
        patch("apps.market.services.news._upsert_items", side_effect=RuntimeError("db down")),
    ):
        items = tv.fetch_news(["AAPL"], limit=5)
    assert len(items) == 1
    assert items[0]["headline"] == "Persist fail"


def test_fetch_earnings_rows_for_events_upsert():
    raw = {
        "events": [
            {
                "symbol": "NASDAQ:NVDA",
                "date": "2026-11-19",
                "time": "after market close",
                "eps_estimate": "0.84",
                "revenue_estimate": 2.6e10,
            },
            {"symbol": "NASDAQ:NVDA", "date": None},
        ]
    }
    with (
        _tools({"get_earnings_calendar": raw}) as c,
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:NVDA"),
    ):
        rows = tv.fetch_earnings(["NVDA"])
    assert c.call_args.args == ("get_earnings_calendar", {"symbols": ["NASDAQ:NVDA"]})
    assert rows == [
        {
            "symbol": "NVDA",
            "date": "2026-11-19",
            "hour": "amc",
            "epsEstimate": 0.84,
            "revenueEstimate": 2.6e10,
        }
    ]


def test_fetch_earnings_accepts_epoch_dates_and_bmo():
    raw = [{"symbol": "NASDAQ:NVDA", "timestamp": 1_760_000_000, "session": "pre-market"}]
    with (
        _tools({"get_earnings_calendar": raw}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:NVDA"),
    ):
        rows = tv.fetch_earnings(["NVDA"])
    assert rows[0]["date"] == "2025-10-09" and rows[0]["hour"] == "bmo"


def test_fetch_earnings_skips_row_that_raises_during_normalization():
    # _date_str/_float/_session_hint are all exception-safe, so drive an exception
    # through the loop body directly to prove a single bad row can't abort the batch.
    raw = {
        "events": [
            {"symbol": "NASDAQ:NVDA", "date": "2026-11-19", "time": "amc"},
            {"symbol": "NASDAQ:NVDA", "date": "2026-11-20", "time": "amc"},
        ]
    }
    with (
        _tools({"get_earnings_calendar": raw}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:NVDA"),
        patch(
            "apps.market.services.tradingview._session_hint",
            side_effect=[RuntimeError("boom"), "amc"],
        ),
    ):
        rows = tv.fetch_earnings(["NVDA"])
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-11-20"


def test_fetch_economic_calendar_rows_for_macro_upsert():
    raw = {
        "events": [
            {
                "title": "Consumer Price Index (MoM)",
                "country": "US",
                "importance": "high",
                "date": "2026-10-14T12:30:00Z",
                "forecast": "0.3",
                "previous": 0.2,
                "actual": None,
            },
            {"title": "no time"},
        ]
    }
    with _tools({"get_economic_calendar": raw}) as c:
        rows = tv.fetch_economic_calendar(ahead_days=10)
    args = c.call_args.args[1]
    assert args["countries"] == ["US"] and "from_date" in args and "to_date" in args
    assert rows == [
        {
            "event": "Consumer Price Index (MoM)",
            "impact": "high",
            "country": "US",
            "time": "2026-10-14T12:30:00+00:00",
            "estimate": 0.3,
            "prev": 0.2,
            "actual": None,
        }
    ]


def test_fetch_economic_calendar_skips_row_that_raises_during_normalization():
    # _iso_datetime/_float are exception-safe, so drive an exception through the
    # loop body directly to prove a single bad row can't abort the batch.
    raw = {
        "events": [
            {"title": "Bad", "country": "US", "importance": "high", "date": "2026-10-14T12:30:00Z"},
            {
                "title": "Consumer Price Index (MoM)",
                "country": "US",
                "importance": "high",
                "date": "2026-10-15T12:30:00Z",
                "forecast": "0.3",
                "previous": 0.2,
                "actual": None,
            },
        ]
    }
    with (
        _tools({"get_economic_calendar": raw}),
        patch(
            "apps.market.services.tradingview._iso_datetime",
            side_effect=[RuntimeError("boom"), "2026-10-15T12:30:00+00:00"],
        ),
    ):
        rows = tv.fetch_economic_calendar(ahead_days=10)
    assert len(rows) == 1
    assert rows[0]["event"] == "Consumer Price Index (MoM)"


def test_calendar_failures_return_empty():
    boom = lambda a: (_ for _ in ()).throw(RuntimeError("x"))  # noqa: E731
    with (
        _tools({"get_earnings_calendar": boom, "get_economic_calendar": boom}),
        patch("apps.market.services.tradingview.to_tv_symbol", return_value="NASDAQ:NVDA"),
    ):
        assert tv.fetch_earnings(["NVDA"]) == []
        assert tv.fetch_economic_calendar() == []
