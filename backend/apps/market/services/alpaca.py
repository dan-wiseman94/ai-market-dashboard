"""Alpaca market data: quotes (snapshots) and OHLC bars via the free IEX feed.

Sourced from Alpaca Data API v2 (https://data.alpaca.markets):
- GET /v2/stocks/snapshots?symbols=...&feed=iex  → latest trade/quote/bar per symbol
- GET /v2/stocks/bars?symbols=...&timeframe=...&feed=iex  → OHLC history

Cached per TTL kind (quotes→5s, ohlc_*→per-timeframe). Persists OHLCBar rows on
each real bars fetch. Never raises — returns {} or [] on any failure.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.secrets.models import ApiCredential

log = logging.getLogger(__name__)

ALPACA_BASE = "https://data.alpaca.markets"

# Map our internal timeframe codes to Alpaca's timeframe strings.
_ALPACA_TIMEFRAME: dict[str, str] = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "1h": "1Hour",
    "1d": "1Day",
}


def _credentials() -> tuple[str | None, str | None]:
    """Return (api_key, api_secret) from the stored credential row.

    Returns (None, None) when the row is absent or either value is missing.
    """
    try:
        cred = ApiCredential.objects.get(provider="alpaca")
    except ApiCredential.DoesNotExist:
        return None, None
    token = cred.token or {}
    api_key = token.get("api_key")
    api_secret = token.get("api_secret")
    if not api_key or not api_secret:
        return None, None
    return api_key, api_secret


def _auth_headers(api_key: str, api_secret: str) -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": api_secret,
    }


def _get(path: str, params: dict, headers: dict) -> dict:
    resp = requests.get(f"{ALPACA_BASE}{path}", params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------
# Canned fixtures (MOCK_EXTERNAL / e2e mode)
# ---------------------------------------------------------------------------


def _canned_quotes(tickers: list[str]) -> dict[str, dict]:
    """Deterministic quotes fixture covering AAPL and MSFT; others get a generic row."""
    seed: dict[str, dict] = {
        "AAPL": {
            "last": 189.30,
            "bid": 189.28,
            "ask": 189.32,
            "volume": 48_312_100,
            "high": 190.10,
            "low": 188.45,
            "pct_change": 0.72,
        },
        "MSFT": {
            "last": 415.60,
            "bid": 415.55,
            "ask": 415.65,
            "volume": 21_045_000,
            "high": 416.80,
            "low": 413.90,
            "pct_change": -0.31,
        },
    }
    return {
        t: seed.get(
            t,
            {
                "last": 100.0,
                "bid": 99.9,
                "ask": 100.1,
                "volume": 1_000_000,
                "high": 101.0,
                "low": 99.0,
                "pct_change": 0.0,
            },
        )
        for t in tickers
    }


def _canned_bars(ticker: str) -> list[dict]:
    """Deterministic 2-bar fixture for MOCK_EXTERNAL / e2e mode."""
    return [
        {
            "open": 188.00,
            "high": 190.50,
            "low": 187.50,
            "close": 189.30,
            "volume": 45_000_000,
            "ts": "2026-05-29T20:00:00+00:00",
        },
        {
            "open": 189.30,
            "high": 191.00,
            "low": 188.80,
            "close": 190.75,
            "volume": 47_500_000,
            "ts": "2026-05-30T20:00:00+00:00",
        },
    ]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _normalize_snapshot(symbol: str, blob: dict) -> dict:
    """Map one Alpaca snapshot blob to the quotes contract dict."""
    latest_trade = blob.get("latestTrade") or {}
    latest_quote = blob.get("latestQuote") or {}
    daily_bar = blob.get("dailyBar") or {}
    prev_bar = blob.get("prevDailyBar") or {}

    last = latest_trade.get("p")
    bid = latest_quote.get("bp")
    ask = latest_quote.get("ap")
    volume_raw = daily_bar.get("v")
    volume = int(volume_raw) if volume_raw is not None else None
    high = daily_bar.get("h")
    low = daily_bar.get("l")

    prev_close = prev_bar.get("c")
    curr_close = daily_bar.get("c")
    if prev_close and curr_close is not None:
        try:
            pct_change = (float(curr_close) - float(prev_close)) / float(prev_close) * 100
        except (TypeError, ZeroDivisionError, ValueError):
            pct_change = None
    else:
        pct_change = None

    return {
        "last": last,
        "bid": bid,
        "ask": ask,
        "volume": volume,
        "high": high,
        "low": low,
        "pct_change": pct_change,
    }


def _normalize_bars(raw_bars: list[dict]) -> list[dict]:
    """Map Alpaca bar objects to the bars contract list."""
    result: list[dict] = []
    for b in raw_bars:
        result.append(
            {
                "open": b.get("o"),
                "high": b.get("h"),
                "low": b.get("l"),
                "close": b.get("c"),
                "volume": int(b["v"]) if b.get("v") is not None else None,
                "ts": b.get("t"),
            }
        )
    return result


# ---------------------------------------------------------------------------
# OHLCBar persist helper (verbatim from spec)
# ---------------------------------------------------------------------------


def _persist_bars(ticker: str, timeframe: str, bars: list[dict]) -> None:
    from apps.market.models import OHLCBar

    rows: list[OHLCBar] = []
    for b in bars:
        try:
            if any(b.get(k) is None for k in ("open", "high", "low", "close", "volume", "ts")):
                continue
            rows.append(
                OHLCBar(
                    ticker=ticker,
                    timeframe=timeframe,
                    open=Decimal(str(b["open"])),
                    high=Decimal(str(b["high"])),
                    low=Decimal(str(b["low"])),
                    close=Decimal(str(b["close"])),
                    volume=int(b["volume"]),
                    ts=datetime.fromisoformat(b["ts"]),
                )
            )
        except (InvalidOperation, ValueError, TypeError) as exc:
            log.warning("alpaca.persist.skip_bar ticker=%s ts=%s: %s", ticker, b.get("ts"), exc)
    if not rows:
        return
    OHLCBar.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["ticker", "timeframe", "ts"],
        update_fields=["open", "high", "low", "close", "volume"],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_quotes(tickers: list[str]) -> dict[str, dict]:
    """Return {ticker: quotes-contract} for each ticker via Alpaca snapshots endpoint.

    Uses the free IEX feed. Returns {} on missing credentials or any fetch error.
    Returns deterministic canned data in mock mode.
    """
    from apps.core.mocks import is_mock_mode

    if not tickers:
        return {}

    if is_mock_mode():
        return _canned_quotes(tickers)

    api_key, api_secret = _credentials()
    if not api_key or not api_secret:
        log.info("market.alpaca: no credential configured, skipping quotes fetch")
        return {}

    symbols = ",".join(t.upper() for t in tickers)
    headers = _auth_headers(api_key, api_secret)
    try:
        body = cache.get_or_fetch(
            f"market:alpaca:snapshots:{symbols}",
            ttl_seconds=cache.ttl_for_kind("quotes"),
            fetcher=lambda: _get(
                "/v2/stocks/snapshots",
                {"symbols": symbols, "feed": "iex"},
                headers,
            ),
        )
    except Exception as exc:
        log.warning("market.alpaca.fetch_quotes failed: %s", exc)
        return {}

    out: dict[str, dict] = {}
    for symbol, blob in (body or {}).items():
        if not isinstance(blob, dict):
            continue
        out[symbol] = _normalize_snapshot(symbol, blob)
    return out


def fetch_bars(ticker: str, *, timeframe: str = "1d", limit: int = 60) -> list[dict]:
    """Return a list of OHLC bar dicts (oldest→newest) for the given ticker.

    Uses the free IEX feed. Persists bars to OHLCBar on each real fetch.
    Returns [] on missing credentials, unsupported timeframe, or any fetch error.
    Returns deterministic canned data in mock mode.
    """
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        return _canned_bars(ticker)

    alpaca_tf = _ALPACA_TIMEFRAME.get(timeframe)
    if alpaca_tf is None:
        log.warning("market.alpaca.fetch_bars: unsupported timeframe %s", timeframe)
        return []

    api_key, api_secret = _credentials()
    if not api_key or not api_secret:
        log.info("market.alpaca: no credential configured, skipping bars fetch")
        return []

    ticker_upper = ticker.upper()
    headers = _auth_headers(api_key, api_secret)
    try:
        body = cache.get_or_fetch(
            f"market:alpaca:bars:{ticker_upper}:{timeframe}:{limit}",
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
            fetcher=lambda: _get(
                "/v2/stocks/bars",
                {
                    "symbols": ticker_upper,
                    "timeframe": alpaca_tf,
                    "limit": limit,
                    "feed": "iex",
                    "sort": "asc",
                },
                headers,
            ),
        )
    except Exception as exc:
        log.warning("market.alpaca.fetch_bars failed ticker=%s: %s", ticker_upper, exc)
        return []

    raw_bars = (body.get("bars") or {}).get(ticker_upper, [])
    bars = _normalize_bars(raw_bars)
    _persist_bars(ticker_upper, timeframe, bars)
    return bars
