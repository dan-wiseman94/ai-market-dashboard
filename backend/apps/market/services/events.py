"""Market events: earnings dates + curated US macro. Mirrors news.py's source pattern."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.models import MarketEvent
from apps.market.services.events_seed import SEED_MACRO_EVENTS
from apps.secrets.credentials import decrypt_token

log = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_api_key() -> str | None:
    return (decrypt_token("finnhub") or {}).get("api_key")


def _finnhub_get(path: str, params: dict, api_key: str) -> dict:
    params = {**params, "token": api_key}
    resp = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


def _earnings_event_time(d: str, hour: str) -> datetime:
    """Finnhub earnings calendar is date-only; place at a representative UTC time per session."""
    base = datetime.fromisoformat(d).replace(tzinfo=UTC)
    if hour == "bmo":
        return base.replace(hour=13, minute=0)  # ~before US open
    if hour == "amc":
        return base.replace(hour=21, minute=0)  # ~after US close
    return base.replace(hour=20, minute=0)  # unknown -> end of US session


def _upsert_earnings(rows: list[dict]) -> list[MarketEvent]:
    out: list[MarketEvent] = []
    for r in rows:
        symbol = (r.get("symbol") or "").upper()
        d = r.get("date")
        if not symbol or not d:
            continue
        hour = (r.get("hour") or "").lower()
        labelled = hour in ("bmo", "amc")
        obj, _ = MarketEvent.objects.update_or_create(
            source="finnhub",
            external_id=f"EARN:{symbol}:{d}",
            defaults={
                "kind": "earnings",
                "ticker": symbol,
                "title": f"{symbol} earnings" + (f" ({hour.upper()})" if labelled else ""),
                "event_time": _earnings_event_time(d, hour),
                "when_hint": hour if labelled else "",
                "impact": "high",
                "detail": {
                    "eps_est": r.get("epsEstimate"),
                    "eps_actual": r.get("epsActual"),
                    "rev_est": r.get("revenueEstimate"),
                },
            },
        )
        out.append(obj)
    return out


def _canned_earnings() -> list[dict]:
    soon = (datetime.now(UTC).date() + timedelta(days=2)).isoformat()
    return [
        {
            "symbol": "NVDA",
            "date": soon,
            "hour": "amc",
            "epsEstimate": 0.84,
            "epsActual": None,
            "revenueEstimate": 2.6e10,
        }
    ]


def fetch_earnings(tickers: list[str], *, ahead_days: int = 30) -> list[MarketEvent]:
    """Fetch + upsert upcoming earnings for `tickers`. Returns the upserted rows."""
    from apps.core.mocks import is_mock_mode, run_service_scenario

    if is_mock_mode():
        run_service_scenario("finnhub")
        return _upsert_earnings(_canned_earnings())

    api_key = _finnhub_api_key()
    if not api_key:
        log.info("Finnhub credential not configured; no earnings fetched")
        return []

    today = datetime.now(UTC).date()
    end = today + timedelta(days=ahead_days)
    out: list[MarketEvent] = []
    for ticker in [t.upper() for t in tickers if t]:
        body = cache.get_or_fetch(
            f"market:earn:{ticker}:{ahead_days}",
            ttl_seconds=cache.ttl_for_kind("events"),
            fetcher=lambda t=ticker: _finnhub_get(
                "/calendar/earnings",
                {"symbol": t, "from": str(today), "to": str(end)},
                api_key,
            ),
        )
        out.extend(_upsert_earnings(body.get("earningsCalendar", [])))
    return out


_MACRO_MAP = [
    ("fomc", "fomc"),
    ("federal funds", "fomc"),
    ("interest rate decision", "fomc"),
    ("cpi", "cpi"),
    ("consumer price", "cpi"),
    ("non-farm", "nfp"),
    ("nonfarm", "nfp"),
    ("payroll", "nfp"),
    ("pce", "pce"),
    ("personal consumption", "pce"),
    ("gdp", "gdp"),
]


def _macro_kind(event_name: str) -> str | None:
    name = (event_name or "").lower()
    for needle, kind in _MACRO_MAP:
        if needle in name:
            return kind
    return None


def _is_high_impact(impact) -> bool:
    return str(impact).lower() in ("high", "3")


def _is_us(country) -> bool:
    return str(country or "").upper() in ("US", "USA", "UNITED STATES")


def _parse_macro_time(t: str) -> datetime | None:
    t = (t or "").strip()
    if not t:
        return None
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _upsert_macro(rows: list[dict], *, source: str) -> list[MarketEvent]:
    out: list[MarketEvent] = []
    for r in rows:
        kind = _macro_kind(r.get("event", ""))
        if kind is None or not _is_high_impact(r.get("impact")) or not _is_us(r.get("country")):
            continue
        dt = _parse_macro_time(r.get("time", ""))
        if dt is None:
            continue
        obj, _ = MarketEvent.objects.update_or_create(
            source=source,
            external_id=f"{kind.upper()}:{dt.date().isoformat()}",
            defaults={
                "kind": kind,
                "ticker": "",
                "title": r.get("event") or kind.upper(),
                "event_time": dt,
                "when_hint": "",
                "impact": "high",
                "detail": {
                    "forecast": r.get("estimate"),
                    "prior": r.get("prev"),
                    "actual": r.get("actual"),
                },
            },
        )
        out.append(obj)
    return out


def fetch_macro(*, ahead_days: int = 45) -> list[MarketEvent]:
    """Fetch + upsert curated US high-impact macro. Falls back to SEED_MACRO_EVENTS if empty."""
    from apps.core.mocks import is_mock_mode, run_service_scenario

    if is_mock_mode():
        run_service_scenario("finnhub")
        return _upsert_macro(SEED_MACRO_EVENTS, source="finnhub")

    api_key = _finnhub_api_key()
    today = datetime.now(UTC).date()
    end = today + timedelta(days=ahead_days)
    rows: list[dict] = []
    if api_key:
        try:
            body = cache.get_or_fetch(
                f"market:macro:{ahead_days}",
                ttl_seconds=cache.ttl_for_kind("events"),
                fetcher=lambda: _finnhub_get(
                    "/calendar/economic", {"from": str(today), "to": str(end)}, api_key
                ),
            )
            rows = body.get("economicCalendar", [])
        except Exception as exc:
            log.warning("market.events.macro_fetch_failed: %s", exc)

    upserted = _upsert_macro(rows, source="finnhub")
    if not upserted:
        upserted = _upsert_macro(SEED_MACRO_EVENTS, source="seed")
    return upserted


MACRO_KINDS = ["fomc", "cpi", "nfp", "pce", "gdp"]


def _serialize_event(e: MarketEvent, today) -> dict:
    return {
        "kind": e.kind,
        "ticker": e.ticker,
        "title": e.title,
        "event_time": e.event_time.isoformat(),
        "days_until": (e.event_time.date() - today).days,
        "when_hint": e.when_hint,
        "impact": e.impact,
        "detail": e.detail,
    }


def upcoming_events(
    tickers: list[str], *, within_days: int = 14, include_macro: bool = True
) -> dict:
    """Read upcoming events from the store. Best-effort on-demand earnings fill for cold tickers."""
    from django.utils import timezone

    now = timezone.now()
    today = now.date()
    horizon = now + timedelta(days=within_days)
    tickers = [t.upper() for t in tickers if t]

    for t in tickers:
        if not MarketEvent.objects.filter(kind="earnings", ticker=t, event_time__gte=now).exists():
            try:
                fetch_earnings([t])
            except Exception as exc:
                log.warning("market.events.ondemand_fill_failed %s: %s", t, exc)

    earnings_qs = MarketEvent.objects.filter(
        kind="earnings", ticker__in=tickers, event_time__gte=now, event_time__lte=horizon
    ).order_by("event_time")
    earnings = [_serialize_event(e, today) for e in earnings_qs]

    macro = []
    if include_macro:
        macro_qs = MarketEvent.objects.filter(
            kind__in=MACRO_KINDS, event_time__gte=now, event_time__lte=horizon
        ).order_by("event_time")
        macro = [_serialize_event(e, today) for e in macro_qs]

    return {"earnings": earnings, "macro": macro}
