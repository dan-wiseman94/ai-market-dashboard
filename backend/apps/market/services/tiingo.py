"""Daily EOD price bars and news from Tiingo (free tier).

Sourced from Tiingo (https://api.tiingo.com):
- GET /tiingo/daily/<ticker>/prices?startDate=YYYY-MM-DD&resampleFreq=daily → OHLCV list
- GET /tiingo/news?tickers=...&limit=15 → news list (may need a separate entitlement)

Bars are cached at ohlc_1d TTL and persisted to OHLCBar via _persist_bars.
News is cached at news TTL and upserted into NewsItem.
Never raises — returns [] on any failure or missing credential.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.services._bars import persist_bars
from apps.secrets.credentials import decrypt_token

log = logging.getLogger(__name__)

TIINGO_BASE = "https://api.tiingo.com"


def _api_key() -> str | None:
    return (decrypt_token("tiingo") or {}).get("api_key")


def _auth_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Token {api_key}",
        "Content-Type": "application/json",
    }


def _get(path: str, params: dict, api_key: str) -> list[dict]:
    resp = requests.get(
        f"{TIINGO_BASE}{path}",
        params=params,
        headers=_auth_headers(api_key),
        timeout=10,
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else []


# ---------------------------------------------------------------------------
# OHLCBar persistence (verbatim from spec contract)
# ---------------------------------------------------------------------------


def _persist_bars(ticker: str, timeframe: str, bars: list[dict]) -> None:
    persist_bars(ticker, timeframe, bars, source="tiingo")


def _normalize_bar(raw: dict) -> dict | None:
    """Map one Tiingo daily price entry to the BARS contract dict, or None to skip."""
    date_str = raw.get("date")
    open_ = raw.get("open")
    high = raw.get("high")
    low = raw.get("low")
    close = raw.get("close")
    volume = raw.get("volume")

    if (
        date_str is None
        or open_ is None
        or high is None
        or low is None
        or close is None
        or volume is None
    ):
        return None

    try:
        ts_str = datetime.fromisoformat(date_str).isoformat()
    except (ValueError, TypeError):
        return None

    return {
        "open": float(open_),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": int(volume),
        "ts": ts_str,
    }


def _normalize_news_item(raw: dict) -> dict | None:
    """Map one Tiingo news entry to a normalized dict, or None to skip."""
    item_id = raw.get("id")
    if item_id is None:
        return None

    published_raw = raw.get("publishedDate") or ""
    try:
        published_at = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None

    tickers: list[str] = raw.get("tickers") or []
    ticker = tickers[0].upper() if tickers else ""

    return {
        "external_id": str(item_id),
        "headline": (raw.get("title") or "")[:512],
        "summary": raw.get("description") or "",
        "url": (raw.get("url") or "")[:1024],
        "source": (raw.get("source") or "")[:64],
        "published_at": published_at,
        "ticker": ticker,
    }


def _canned_bars(ticker: str, days: int) -> list[dict]:
    """Deterministic EOD bar fixture for MOCK_EXTERNAL mode."""
    return [
        {
            "open": 150.0,
            "high": 155.0,
            "low": 148.0,
            "close": 152.5,
            "volume": 50_000_000,
            "ts": "2026-01-02T00:00:00+00:00",
        }
    ]


def _canned_news(tickers: list[str], limit: int) -> list[dict]:
    """Deterministic news fixture for MOCK_EXTERNAL mode."""
    ticker = tickers[0].upper() if tickers else "AAPL"
    return [
        {
            "external_id": "tiingo-mock-1",
            "headline": f"Mock Tiingo headline for {ticker}",
            "summary": "Mocked summary for E2E tests.",
            "url": "https://example.com/tiingo-mock-1",
            "source": "MockSource",
            "published_at": datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
            "ticker": ticker,
        }
    ][:limit]


def fetch_daily_bars(ticker: str, *, days: int = 120) -> list[dict]:
    """Fetch and persist daily EOD bars for `ticker` from Tiingo.

    Returns a list of BARS-contract dicts (oldest → newest), [] on failure.
    Persists to OHLCBar on each real fetch (idempotent upsert).
    In mock mode returns a deterministic canned bar list without persisting.
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()

    if is_mock_mode():
        return _canned_bars(ticker, days)

    api_key = _api_key()
    if not api_key:
        log.info("market.tiingo: no credential configured, skipping fetch_daily_bars")
        return []

    start_date_str = (datetime.now(UTC).date() - timedelta(days=days)).isoformat()

    try:
        raw_bars = cache.get_or_fetch(
            f"market:tiingo:bars:{ticker}:{days}",
            ttl_seconds=cache.ttl_for_kind("ohlc_1d"),
            fetcher=lambda: _get(
                f"/tiingo/daily/{ticker}/prices",
                {"startDate": start_date_str, "resampleFreq": "daily"},
                api_key,
            ),
        )
    except Exception as exc:
        log.warning("market.tiingo.fetch_daily_bars.failed ticker=%s: %s", ticker, exc)
        return []

    bars: list[dict] = []
    for raw in raw_bars:
        normalized = _normalize_bar(raw)
        if normalized is not None:
            bars.append(normalized)

    _persist_bars(ticker, "1d", bars)
    return bars


def fetch_news(tickers: list[str], *, limit: int = 15) -> list[dict]:
    """Fetch news for `tickers` from the Tiingo News API.

    Returns newest-first list of normalized dicts (capped at `limit`), upserts
    NewsItem rows. Returns [] on missing credential, network error, or if the
    Tiingo news entitlement is unavailable on the account.
    In mock mode returns a deterministic canned list without DB writes.
    """
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _canned_news(tickers, limit)

    api_key = _api_key()
    if not api_key:
        log.info("market.tiingo: no credential configured, skipping fetch_news")
        return []

    tickers_upper = [t.upper() for t in tickers if t]
    if not tickers_upper:
        return []

    tickers_param = ",".join(t.lower() for t in tickers_upper)

    try:
        raw_items = cache.get_or_fetch(
            f"market:tiingo:news:{tickers_param}:{limit}",
            ttl_seconds=cache.ttl_for_kind("news"),
            fetcher=lambda: _get(
                "/tiingo/news",
                {"tickers": tickers_param, "limit": limit},
                api_key,
            ),
        )
    except Exception as exc:
        log.warning("market.tiingo.fetch_news.failed tickers=%s: %s", tickers_param, exc)
        return []

    from apps.market.models import NewsItem

    results: list[dict] = []
    for raw in raw_items:
        normalized = _normalize_news_item(raw)
        if normalized is None:
            continue
        try:
            NewsItem.objects.update_or_create(
                provider="tiingo",
                external_id=normalized["external_id"],
                defaults={
                    "ticker": normalized["ticker"],
                    "headline": normalized["headline"],
                    "summary": normalized["summary"],
                    "url": normalized["url"],
                    "source": normalized["source"],
                    "published_at": normalized["published_at"],
                },
            )
        except Exception as exc:
            log.warning(
                "market.tiingo.news.upsert_failed id=%s: %s", normalized["external_id"], exc
            )
        results.append(normalized)

    results.sort(key=lambda x: x["published_at"], reverse=True)
    return results[:limit]
