"""Market data read endpoints."""
from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.market.schwab_client import SchwabNotConnectedError
from apps.market.services.chain import fetch_chain
from apps.market.services.context import fetch_market_context
from apps.market.services.news import fetch_news
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes


def _err(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"code": code, "message": message}, status=status)


def _wrap_schwab(fn):
    """Decorator: catch SchwabNotConnectedError and return 503."""
    def inner(request: HttpRequest, *args, **kwargs):
        try:
            return fn(request, *args, **kwargs)
        except SchwabNotConnectedError as e:
            return _err("schwab_not_connected", str(e), 503)
    return inner


@require_GET
@_wrap_schwab
def quotes(request: HttpRequest) -> JsonResponse:
    tickers = request.GET.get("tickers", "").strip()
    if not tickers:
        return _err("missing_tickers", "Provide ?tickers=SPY,QQQ", 400)
    ticker_list = [t for t in tickers.split(",") if t]
    return JsonResponse(fetch_quotes(ticker_list))


@require_GET
@_wrap_schwab
def ohlc(request: HttpRequest) -> JsonResponse:
    ticker = request.GET.get("ticker", "").strip()
    timeframe = request.GET.get("timeframe", "1m")
    try:
        bars = int(request.GET.get("bars", "60"))
    except ValueError:
        return _err("invalid_bars", "bars must be an integer", 400)
    if not ticker:
        return _err("missing_ticker", "Provide ?ticker=", 400)
    try:
        result = fetch_ohlc(ticker, timeframe=timeframe, bars=bars)
    except ValueError as e:
        return _err("invalid_timeframe", str(e), 400)
    return JsonResponse({"ticker": ticker.upper(), "timeframe": timeframe, "bars": result})


@require_GET
@_wrap_schwab
def positions(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(fetch_positions(), safe=False)


@require_GET
@_wrap_schwab
def context(_request: HttpRequest) -> JsonResponse:
    return JsonResponse(fetch_market_context())


@require_GET
@_wrap_schwab
def chain(request: HttpRequest) -> JsonResponse:
    ticker = request.GET.get("ticker", "").strip()
    if not ticker:
        return _err("missing_ticker", "Provide ?ticker=", 400)
    return JsonResponse(fetch_chain(ticker))


@require_GET
def news(request: HttpRequest) -> JsonResponse:
    raw_tickers = request.GET.get("tickers", "").strip()
    tickers = [t.strip() for t in raw_tickers.split(",") if t.strip()]
    try:
        lookback = int(request.GET.get("lookback", "24"))
    except ValueError:
        return _err("invalid_lookback", "lookback must be int hours", 400)
    items = fetch_news(tickers, lookback_hours=lookback)
    return JsonResponse({"items": items})
