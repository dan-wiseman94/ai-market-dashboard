"""Corporate actions: stock splits + dividends from Finnhub. Mirrors events.py.

Splits and dividends are stored as :class:`apps.market.models.CorporateAction`
rows keyed by ex-date and consumed by :mod:`apps.market.returns` to keep forward
returns honest (a 3:1 split must not read as a -66% crash).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from functools import partial

import requests  # type: ignore[import-untyped]
from django.utils import timezone

from apps.market import cache
from apps.market.models import CorporateAction
from apps.market.services.safe_log import safe_err
from apps.secrets.credentials import decrypt_token

log = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"

# How far back/ahead the scheduled refresh and on-demand fill look. Back covers the
# longest post-mortem horizon (90d) with generous slack for cold-ticker backfill.
DEFAULT_BACK_DAYS = 400
DEFAULT_AHEAD_DAYS = 10


def _finnhub_api_key() -> str | None:
    return (decrypt_token("finnhub") or {}).get("api_key")


def _finnhub_get_list(path: str, params: dict, api_key: str) -> list[dict]:
    """GET a Finnhub endpoint that returns a JSON array (split/dividend feeds)."""
    params = {**params, "token": api_key}
    resp = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else []


def _split_ratio(from_factor, to_factor) -> float | None:
    """shares_after / shares_before. 3:1 forward → (from=1,to=3) → 3.0; 1:10 reverse → 0.1."""
    try:
        f = float(from_factor)
        t = float(to_factor)
    except (TypeError, ValueError):
        return None
    if f <= 0 or t <= 0:
        return None
    return t / f


def _upsert_splits(rows: list[dict]) -> list[CorporateAction]:
    out: list[CorporateAction] = []
    for r in rows:
        symbol = (r.get("symbol") or "").upper()
        d = r.get("date")
        ratio = _split_ratio(r.get("fromFactor"), r.get("toFactor"))
        if not symbol or not d or ratio is None or ratio == 1.0:
            # ratio == 1.0 is an economic no-op; skip to avoid storing inert rows.
            continue
        obj, _ = CorporateAction.objects.update_or_create(
            source="finnhub",
            external_id=f"SPLIT:{symbol}:{d}",
            defaults={
                "kind": "split",
                "ticker": symbol,
                "ex_date": date.fromisoformat(d),
                "ratio": ratio,
                "amount": None,
                "detail": {"fromFactor": r.get("fromFactor"), "toFactor": r.get("toFactor")},
            },
        )
        out.append(obj)
    return out


def _upsert_dividends(rows: list[dict]) -> list[CorporateAction]:
    out: list[CorporateAction] = []
    for r in rows:
        symbol = (r.get("symbol") or "").upper()
        d = r.get("date")  # ex-dividend date
        amount = r.get("amount")
        if not symbol or not d or amount is None:
            continue
        try:
            amt = float(amount)
        except (TypeError, ValueError):
            continue
        if amt <= 0:
            continue
        obj, _ = CorporateAction.objects.update_or_create(
            source="finnhub",
            external_id=f"DIV:{symbol}:{d}",
            defaults={
                "kind": "dividend",
                "ticker": symbol,
                "ex_date": date.fromisoformat(d),
                "ratio": None,
                "amount": amt,
                "detail": {
                    "adjustedAmount": r.get("adjustedAmount"),
                    "payDate": r.get("payDate"),
                    "currency": r.get("currency"),
                },
            },
        )
        out.append(obj)
    return out


def _canned_splits() -> list[dict]:
    recent = (datetime.now(UTC).date() - timedelta(days=3)).isoformat()
    return [{"symbol": "NVDA", "date": recent, "fromFactor": 1, "toFactor": 10}]


def _canned_dividends() -> list[dict]:
    recent = (datetime.now(UTC).date() - timedelta(days=3)).isoformat()
    return [{"symbol": "AAPL", "date": recent, "amount": 0.25, "currency": "USD"}]


def _window(back_days: int, ahead_days: int) -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=back_days), today + timedelta(days=ahead_days)


def fetch_splits(
    tickers: list[str], *, back_days: int = DEFAULT_BACK_DAYS, ahead_days: int = DEFAULT_AHEAD_DAYS
) -> list[CorporateAction]:
    """Fetch + upsert splits for `tickers`. Returns the upserted rows."""
    from apps.core.mocks import is_mock_mode, run_service_scenario

    if is_mock_mode():
        run_service_scenario("finnhub")
        return _upsert_splits(_canned_splits())

    api_key = _finnhub_api_key()
    if not api_key:
        log.info("Finnhub credential not configured; no splits fetched")
        return []

    start, end = _window(back_days, ahead_days)
    out: list[CorporateAction] = []
    for ticker in [t.upper() for t in tickers if t]:
        body = cache.get_or_fetch(
            f"market:split:{ticker}:{back_days}:{ahead_days}",
            ttl_seconds=cache.ttl_for_kind("corporate_actions"),
            fetcher=partial(
                _finnhub_get_list,
                "/stock/split",
                {"symbol": ticker, "from": str(start), "to": str(end)},
                api_key,
            ),
        )
        out.extend(_upsert_splits(body))
    return out


def fetch_dividends(
    tickers: list[str], *, back_days: int = DEFAULT_BACK_DAYS, ahead_days: int = DEFAULT_AHEAD_DAYS
) -> list[CorporateAction]:
    """Fetch + upsert dividends for `tickers`. Returns the upserted rows."""
    from apps.core.mocks import is_mock_mode, run_service_scenario

    if is_mock_mode():
        run_service_scenario("finnhub")
        return _upsert_dividends(_canned_dividends())

    api_key = _finnhub_api_key()
    if not api_key:
        log.info("Finnhub credential not configured; no dividends fetched")
        return []

    start, end = _window(back_days, ahead_days)
    out: list[CorporateAction] = []
    for ticker in [t.upper() for t in tickers if t]:
        body = cache.get_or_fetch(
            f"market:div:{ticker}:{back_days}:{ahead_days}",
            ttl_seconds=cache.ttl_for_kind("corporate_actions"),
            fetcher=partial(
                _finnhub_get_list,
                "/stock/dividend",
                {"symbol": ticker, "from": str(start), "to": str(end)},
                api_key,
            ),
        )
        out.extend(_upsert_dividends(body))
    return out


def corporate_actions_for(
    ticker: str, start: datetime, end: datetime, *, kind: str | None = None
) -> list[CorporateAction]:
    """Stored corporate actions for `ticker` with ``start.date() < ex_date <= end.date()``.

    Best-effort on-demand fill: if the ticker has no stored actions at all, fetch
    once (cold-ticker backfill) before reading — mirrors ``upcoming_events``. A
    fetch failure degrades to whatever is already stored (possibly none), never raises.
    """
    ticker = (ticker or "").upper()
    if not ticker:
        return []

    if not CorporateAction.objects.filter(ticker=ticker).exists():
        try:
            fetch_splits([ticker])
            fetch_dividends([ticker])
        except Exception as exc:  # network / parse — degrade to stored
            log.warning(
                "market.corporate_actions.ondemand_fill_failed %s: %s", ticker, safe_err(exc)
            )

    qs = CorporateAction.objects.filter(
        ticker=ticker, ex_date__gt=start.date(), ex_date__lte=end.date()
    )
    if kind is not None:
        qs = qs.filter(kind=kind)
    return list(qs.order_by("ex_date"))


def prune_old(*, before_days: int = DEFAULT_BACK_DAYS + 60) -> int:
    """Delete actions whose ex-date is older than the longest window we'd ever read."""
    cutoff = timezone.now().date() - timedelta(days=before_days)
    deleted, _ = CorporateAction.objects.filter(ex_date__lt=cutoff).delete()
    return deleted
