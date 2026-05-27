"""Market events: earnings dates + curated US macro. Mirrors news.py's source pattern."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.models import MarketEvent
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_api_key() -> str | None:
    try:
        cred = ApiCredential.objects.get(provider="finnhub")
    except ApiCredential.DoesNotExist:
        return None
    return (cred.token or {}).get("api_key")


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
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
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
