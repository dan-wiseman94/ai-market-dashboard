"""Market data read endpoints."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
from rest_framework import viewsets

from apps.market.calendar import MARKETS, calendar_for, market_state
from apps.market.models import CalendarOverride
from apps.market.schwab_client import SchwabNotConnectedError
from apps.market.serializers import CalendarOverrideSerializer
from apps.market.services.chain import fetch_chain
from apps.market.services.context import fetch_market_context
from apps.market.services.news import fetch_news
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.events import upcoming_events
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
    raw = request.GET.get("tickers", "").strip()
    if not raw:
        return _err("missing_tickers", "Provide ?tickers=SPY,QQQ", 400)
    return JsonResponse(fetch_quotes([t for t in raw.split(",") if t]))


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
    raw = request.GET.get("tickers", "").strip()
    tickers = [t.strip() for t in raw.split(",") if t.strip()]
    try:
        lookback = int(request.GET.get("lookback", "24"))
    except ValueError:
        return _err("invalid_lookback", "lookback must be int hours", 400)
    return JsonResponse({"items": fetch_news(tickers, lookback_hours=lookback)})


@require_GET
def events(request: HttpRequest) -> JsonResponse:
    raw = request.GET.get("tickers", "").strip()
    tickers = [t.strip() for t in raw.split(",") if t.strip()]
    try:
        within = int(request.GET.get("within_days", "14"))
    except ValueError:
        return _err("invalid_within_days", "within_days must be an integer", 400)
    include_macro = request.GET.get("include_macro", "true").lower() != "false"
    return JsonResponse(upcoming_events(tickers, within_days=within, include_macro=include_macro))


class CalendarOverrideViewSet(viewsets.ModelViewSet):
    queryset = CalendarOverride.objects.all().order_by("symbol")
    serializer_class = CalendarOverrideSerializer


@require_GET
def calendar_status(request: HttpRequest) -> JsonResponse:
    symbols = request.GET.getlist("symbol")
    markets: set[str] = set(request.GET.getlist("market"))
    for s in symbols:
        markets.add(calendar_for(s))
    if not markets:
        markets.add("us_equity")
        markets.update(CalendarOverride.objects.values_list("market_key", flat=True).distinct())
    out: dict[str, dict] = {}
    for m in sorted(markets):
        if m not in MARKETS:
            continue
        st = market_state(market=m)
        out[m] = {
            "is_open": st.is_open,
            "phase": st.phase,
            "is_early_close": st.is_early_close,
            "next_open": st.next_open.isoformat() if st.next_open else None,
            "next_close": st.next_close.isoformat() if st.next_close else None,
        }
    return JsonResponse({"markets": out})
