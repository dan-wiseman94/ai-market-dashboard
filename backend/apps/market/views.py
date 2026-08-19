"""Market data read endpoints."""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError

from apps.core.http import json_error_response
from apps.market.calendar import MARKETS, calendar_for, market_state
from apps.market.models import CalendarOverride
from apps.market.schwab_client import SchwabNotConnectedError
from apps.market.serializers import CalendarOverrideSerializer
from apps.market.services.chain import fetch_chain
from apps.market.services.context import fetch_market_context
from apps.market.services.edgar import fetch_filings
from apps.market.services.events import upcoming_events
from apps.market.services.fred import fetch_macro
from apps.market.services.news import fetch_news
from apps.market.services.ohlc import fetch_ohlc
from apps.market.services.positions import fetch_positions
from apps.market.services.quotes import fetch_quotes
from apps.market.services.treasury import fetch_treasury


def _err(code: str, message: str, status: int) -> JsonResponse:
    return json_error_response(code, message, status=status)


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
        lookback_hours = int(request.GET.get("lookback_hours", "24"))
    except ValueError:
        return _err("invalid_lookback_hours", "lookback_hours must be an integer", 400)
    return JsonResponse({"items": fetch_news(tickers, lookback_hours=lookback_hours)})


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


@require_GET
def macro(request: HttpRequest) -> JsonResponse:
    """Macro indicators from FRED (CPI, rates, the Treasury yield curve, …).

    Optional ``?series=CPIAUCSL,DGS10`` narrows to specific FRED series ids; default
    returns the curated set. Keyless callers get {} until a FRED key is configured.
    """
    raw = request.GET.get("series", "").strip()
    series = [s.strip().upper() for s in raw.split(",") if s.strip()] or None
    return JsonResponse(fetch_macro(series))


@require_GET
def filings(request: HttpRequest) -> JsonResponse:
    """Recent SEC filings (10-K/10-Q/8-K) per ticker from EDGAR. ``?tickers=AAPL,MSFT``."""
    raw = request.GET.get("tickers", "").strip()
    tickers = [t.strip() for t in raw.split(",") if t.strip()]
    if not tickers:
        return _err("missing_tickers", "Provide ?tickers=AAPL,MSFT", 400)
    return JsonResponse({t.upper(): fetch_filings(t) for t in tickers})


@require_GET
def treasury(_request: HttpRequest) -> JsonResponse:
    """US Treasury FiscalData: average interest rates + debt to the penny (keyless)."""
    return JsonResponse(fetch_treasury())


class CalendarOverrideViewSet(viewsets.ModelViewSet):
    queryset = CalendarOverride.objects.all().order_by("symbol")
    serializer_class = CalendarOverrideSerializer

    # CalendarOverride.symbol (API field "ticker") is unique AND normalized
    # (strip().upper()) in Model.save(), which runs AFTER the serializer's UniqueValidator
    # (which sees the raw value). So a case-variant of an existing ticker ("spy" vs stored
    # "SPY") slips past validation and hits the DB unique constraint -> IntegrityError ->
    # 500. Translate it to a clean 400. (Wrapped in a savepoint so the failed INSERT rolls
    # back cleanly.)
    def perform_create(self, serializer) -> None:
        self._save_or_400(serializer)

    def perform_update(self, serializer) -> None:
        self._save_or_400(serializer)

    @staticmethod
    def _save_or_400(serializer) -> None:
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            raise ValidationError(
                {"ticker": "A calendar override for this ticker already exists."}
            ) from exc


@require_GET
def calendar_status(request: HttpRequest) -> JsonResponse:
    raw = request.GET.get("tickers", "").strip()
    tickers = [t.strip() for t in raw.split(",") if t.strip()]
    markets: set[str] = set(request.GET.getlist("market"))
    for t in tickers:
        markets.add(calendar_for(t))
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
