"""Financial news with per-ticker sentiment from Marketaux (free tier: 100 req/day, ≤3 symbols/req).

Sourced from https://api.marketaux.com/v1:
- GET /news/all?symbols=A,B,C&filter_entities=true&language=en&limit=15&api_token=...

Free plan caps symbols-per-request at 3; tickers are chunked accordingly.
Cached news TTL. Upserts NewsItem on each real fetch (sentiment is NOT stored on the model —
it lives only in the returned dict). Never raises — returns [] on any failure.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.services.safe_log import safe_err
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

MARKETAUX_BASE = "https://api.marketaux.com/v1"

# Free-plan limit: at most 3 symbols per request.
_MAX_SYMBOLS_PER_REQUEST = 3


def _api_key() -> str | None:
    try:
        cred = ApiCredential.objects.get(provider="marketaux")
    except ApiCredential.DoesNotExist:
        return None
    return (cred.token or {}).get("api_key")


def _get(path: str, params: dict) -> dict:
    resp = requests.get(f"{MARKETAUX_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


def _canned_news(tickers: list[str], limit: int) -> list[dict]:
    """Deterministic fixture for MOCK_EXTERNAL / e2e mode."""
    ticker = tickers[0].upper() if tickers else "AAPL"
    return [
        {
            "external_id": "marketaux-mock-uuid-1",
            "headline": f"Mock Marketaux headline for {ticker}",
            "summary": "Mocked summary for E2E tests.",
            "url": "https://example.com/marketaux-mock-1",
            "source": "MockSource",
            "published_at": datetime(2026, 1, 2, 14, 30, tzinfo=UTC),
            "tickers": [ticker],
            "sentiment": {ticker: 0.42},
        }
    ][:limit]


def _parse_published_at(raw: str) -> datetime | None:
    """Parse Marketaux ISO timestamp (may end with 'Z'). Returns None on failure."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _normalize_item(raw: dict) -> dict | None:
    """Map one Marketaux data item to a normalized dict. Returns None to skip."""
    uuid = raw.get("uuid")
    if not uuid:
        return None

    published_at = _parse_published_at(raw.get("published_at") or "")
    if published_at is None:
        return None

    entities: list[dict] = raw.get("entities") or []

    # Derive primary ticker and sentiment map from entities
    entity_symbols = [e["symbol"].upper() for e in entities if e.get("symbol")]
    ticker = entity_symbols[0] if entity_symbols else ""
    sentiment: dict[str, float] = {}
    for e in entities:
        sym = (e.get("symbol") or "").upper()
        score = e.get("sentiment_score")
        if sym and score is not None:
            with contextlib.suppress(ValueError, TypeError):
                sentiment[sym] = float(score)

    return {
        "external_id": str(uuid),
        "headline": (raw.get("title") or "")[:512],
        "summary": raw.get("description") or raw.get("snippet") or "",
        "url": (raw.get("url") or "")[:1024],
        "source": (raw.get("source") or "")[:64],
        "published_at": published_at,
        "ticker": ticker,
        "tickers": entity_symbols,
        "sentiment": sentiment,
    }


def _fetch_chunk(symbols: list[str], api_key: str, limit: int) -> list[dict]:
    """Fetch one chunk of ≤3 symbols from Marketaux. Returns raw data list."""
    symbols_param = ",".join(symbols)
    params = {
        "symbols": symbols_param,
        "filter_entities": "true",
        "language": "en",
        "limit": limit,
        "api_token": api_key,
    }
    body = _get("/news/all", params)
    data = body.get("data") or []
    return data if isinstance(data, list) else []


def fetch_news(tickers: list[str], *, limit: int = 15) -> list[dict]:
    """Fetch financial news with per-ticker sentiment from Marketaux.

    Chunks tickers into groups of ≤3 (free-plan cap), aggregates results,
    deduplicates by uuid, sorts newest-first, caps at `limit`, and upserts
    NewsItem rows. Sentiment lives only in the returned dicts (not on NewsItem).

    Returns [] on missing credential or any network/parse failure.
    In mock mode returns a deterministic canned list with sentiment.
    """
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _canned_news(tickers, limit)

    api_key = _api_key()
    if not api_key:
        log.info("market.marketaux: no credential configured, skipping")
        return []

    tickers_upper = [t.upper() for t in tickers if t]
    if not tickers_upper:
        return []

    # Chunk into groups of ≤3
    chunks: list[list[str]] = [
        tickers_upper[i : i + _MAX_SYMBOLS_PER_REQUEST]
        for i in range(0, len(tickers_upper), _MAX_SYMBOLS_PER_REQUEST)
    ]

    aggregated: list[dict] = []
    try:
        for chunk in chunks:
            cache_key = f"market:marketaux:news:{','.join(chunk)}:{limit}"
            raw_items = cache.get_or_fetch(
                cache_key,
                ttl_seconds=cache.ttl_for_kind("news"),
                fetcher=lambda c=chunk: _fetch_chunk(c, api_key, limit),
            )
            aggregated.extend(raw_items if isinstance(raw_items, list) else [])
    except Exception as exc:
        log.warning("market.marketaux.fetch_failed: %s", safe_err(exc))
        return []

    # Normalize and deduplicate by uuid
    from apps.market.models import NewsItem

    seen: set[str] = set()
    results: list[dict] = []
    for raw in aggregated:
        normalized = _normalize_item(raw)
        if normalized is None:
            continue
        uid = normalized["external_id"]
        if uid in seen:
            continue
        seen.add(uid)

        # Upsert the NewsItem row (no sentiment field on the model)
        try:
            NewsItem.objects.update_or_create(
                provider="marketaux",
                external_id=uid,
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
            log.warning("market.marketaux.upsert_failed id=%s: %s", uid, exc)

        # Build the return dict (include tickers + sentiment not stored in DB)
        results.append(
            {
                "external_id": normalized["external_id"],
                "headline": normalized["headline"],
                "summary": normalized["summary"],
                "url": normalized["url"],
                "source": normalized["source"],
                "published_at": normalized["published_at"],
                "tickers": normalized["tickers"],
                "sentiment": normalized["sentiment"],
            }
        )

    # Sort newest-first
    results.sort(key=lambda x: x["published_at"], reverse=True)
    return results[:limit]
