"""News fetching from Finnhub. One concrete impl, no abstraction (M5 scope)."""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import requests

from apps.market import cache
from apps.market.models import NewsItem
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_api_key() -> str | None:
    try:
        cred = ApiCredential.objects.get(provider="finnhub")
    except ApiCredential.DoesNotExist:
        return None
    token = cred.token or {}
    return token.get("api_key")


def _finnhub_get(path: str, params: dict, api_key: str) -> list[dict]:
    params = {**params, "token": api_key}
    resp = requests.get(f"{FINNHUB_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, list) else []


def _external_id(it: dict) -> str | None:
    raw = it.get("id")
    if raw is None or raw == "":
        return None
    return str(raw)


def _upsert_items(provider: str, items: list[dict]) -> list[NewsItem]:
    out: list[NewsItem] = []
    for it in items:
        external_id = _external_id(it)
        if external_id is None:
            continue
        published_at = datetime.fromtimestamp(it.get("datetime", 0), tz=UTC)
        obj, _ = NewsItem.objects.update_or_create(
            provider=provider, external_id=external_id,
            defaults={
                "ticker": (it.get("related") or "").upper(),
                "headline": (it.get("headline") or "")[:512],
                "summary": it.get("summary") or "",
                "url": (it.get("url") or "")[:1024],
                "source": (it.get("source") or "")[:64],
                "published_at": published_at,
            },
        )
        out.append(obj)
    return out


def fetch_news(
    tickers: list[str],
    *,
    lookback_hours: int = 24,
    limit: int = 15,
) -> list[dict]:
    """Fetch + dedup news for `tickers` plus market-wide. Newest-first list capped at `limit`."""
    api_key = _finnhub_api_key()
    if not api_key:
        log.info("Finnhub credential not configured; returning empty news list")
        return []

    now = datetime.now(UTC)
    end = now.date()
    # Subtract hours from the full datetime, then take the date — so sub-day lookback
    # values still produce a sensible from/to range for Finnhub's date-only endpoint.
    start = (now - timedelta(hours=lookback_hours)).date()
    aggregated: list[dict] = []

    for ticker in [t.upper() for t in tickers if t]:
        cache_key = f"market:news:{ticker}:{lookback_hours}"
        items = cache.get_or_fetch(
            cache_key,
            ttl_seconds=cache.ttl_for_kind("news"),
            fetcher=lambda t=ticker: _finnhub_get(
                "/company-news",
                {"symbol": t, "from": str(start), "to": str(end)},
                api_key,
            ),
        )
        _upsert_items("finnhub", items)
        aggregated.extend(items)

    general = cache.get_or_fetch(
        f"market:news:_general_:{lookback_hours}",
        ttl_seconds=cache.ttl_for_kind("news"),
        fetcher=lambda: _finnhub_get("/news", {"category": "general"}, api_key),
    )
    _upsert_items("finnhub", general)
    aggregated.extend(general)

    seen: set[str] = set()
    deduped: list[dict] = []
    for it in aggregated:
        key = _external_id(it)
        if key is None or key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    deduped.sort(key=lambda it: it.get("datetime", 0), reverse=True)
    return deduped[:limit]
