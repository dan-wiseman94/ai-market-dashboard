"""Quotes and OHLC price history from Twelve Data (free-tier REST API).

Sourced from Twelve Data (https://api.twelvedata.com):
- GET /quote?symbol=A,B,C&apikey=   → real-time quotes (8 req/min, 800 req/day free tier)
- GET /time_series?symbol=X&interval=<tf>&outputsize=N&order=ASC&apikey=
  → OHLC bars, oldest-first

Both endpoints are cached via Redis. Never raises — returns {} or [] on any failure.
Supports equities, FX (EUR/USD), and crypto (BTC/USD) symbols.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

import requests  # type: ignore[import-untyped]

from apps.market import cache
from apps.market.services.safe_log import safe_err
from apps.secrets.credentials import decrypt_token

log = logging.getLogger(__name__)

TWELVEDATA_BASE = "https://api.twelvedata.com"

# Map OUR timeframe codes → Twelve Data interval strings.
_TF_TO_TD: dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "1d": "1day",
}

# Reverse map: Twelve Data interval → OUR timeframe code (used when persisting bars).
_TD_TO_TF: dict[str, str] = {v: k for k, v in _TF_TO_TD.items()}


def _api_key() -> str | None:
    return (decrypt_token("twelvedata") or {}).get("api_key")


def _get(path: str, params: dict) -> dict:
    """GET from Twelve Data; always returns a dict (empty on non-dict body)."""
    resp = requests.get(f"{TWELVEDATA_BASE}{path}", params=params, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _safe_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_int_float(value: object) -> int | None:
    """Parse a numeric string that may have decimals (e.g. "1234567.0") as int."""
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _normalize_quote(raw: dict) -> dict:
    """Build the QUOTES CONTRACT dict from a single Twelve Data quote object."""
    return {
        "last": _safe_float(raw.get("close")),
        "bid": None,  # free /quote endpoint has no bid/ask
        "ask": None,
        "volume": _safe_int_float(raw.get("volume")),
        "high": _safe_float(raw.get("high")),
        "low": _safe_float(raw.get("low")),
        "pct_change": _safe_float(raw.get("percent_change")),
    }


def _normalize_bar(raw: dict) -> dict | None:
    """Convert one time-series value dict to BARS CONTRACT format.

    Returns None when any required field is missing or unparseable.
    """
    dt_str: str = raw.get("datetime", "")
    if not dt_str:
        return None
    # Twelve Data returns "YYYY-MM-DD" for daily bars and "YYYY-MM-DD HH:MM:SS" for intraday.
    if len(dt_str) == 10:
        ts = f"{dt_str}T00:00:00+00:00"
    else:
        try:
            ts = datetime.fromisoformat(dt_str).replace(tzinfo=UTC).isoformat()
        except ValueError:
            return None

    open_ = _safe_float(raw.get("open"))
    high = _safe_float(raw.get("high"))
    low = _safe_float(raw.get("low"))
    close = _safe_float(raw.get("close"))
    volume = _safe_int_float(raw.get("volume"))

    if any(v is None for v in (open_, high, low, close, volume)):
        return None

    return {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "ts": ts,
    }


# ---------------------------------------------------------------------------
# OHLCBar persistence (canonical spec helper — verbatim shape)
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
            log.warning("twelvedata.persist.skip_bar ticker=%s ts=%s: %s", ticker, b.get("ts"), exc)
    if not rows:
        return
    OHLCBar.objects.bulk_create(
        rows,
        update_conflicts=True,
        unique_fields=["ticker", "timeframe", "ts"],
        update_fields=["open", "high", "low", "close", "volume"],
    )


# ---------------------------------------------------------------------------
# Canned fixtures for MOCK_EXTERNAL / e2e mode
# ---------------------------------------------------------------------------


def _canned_quotes(symbols: list[str]) -> dict[str, dict]:
    """Deterministic quote fixture for MOCK_EXTERNAL mode."""
    return {
        sym: {
            "last": 150.0,
            "bid": None,
            "ask": None,
            "volume": 1_000_000,
            "high": 152.0,
            "low": 148.0,
            "pct_change": 1.23,
        }
        for sym in symbols
    }


def _canned_time_series(symbol: str) -> list[dict]:
    """Deterministic bar fixture for MOCK_EXTERNAL mode (5 daily bars)."""
    dates = [
        "2026-05-27",
        "2026-05-28",
        "2026-05-29",
        "2026-05-30",
        "2026-05-31",
    ]
    return [
        {
            "open": 149.0 + i,
            "high": 151.0 + i,
            "low": 148.0 + i,
            "close": 150.0 + i,
            "volume": 1_000_000 + i * 1000,
            "ts": f"{d}T00:00:00+00:00",
        }
        for i, d in enumerate(dates)
    ]


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def fetch_quotes(symbols: list[str]) -> dict[str, dict]:
    """Fetch real-time quotes for one or more equity / FX / crypto symbols.

    Returns a QUOTES CONTRACT dict keyed by symbol. Returns {} on any failure
    (missing credential, network error, unexpected payload). Never raises.

    Twelve Data returns the quote dict directly for a single symbol, and a
    symbol-keyed mapping for multiple symbols; both shapes are handled.
    """
    from apps.core.mocks import is_mock_mode

    if not symbols:
        return {}

    if is_mock_mode():
        return _canned_quotes(symbols)

    api_key = _api_key()
    if not api_key:
        log.info("market.twelvedata: no credential configured, skipping fetch_quotes")
        return {}

    joined = ",".join(s.upper() for s in symbols)
    cache_key = f"market:twelvedata:quotes:{joined}"

    try:
        body = cache.get_or_fetch(
            cache_key,
            ttl_seconds=cache.ttl_for_kind("quotes"),
            fetcher=lambda: _get("/quote", {"symbol": joined, "apikey": api_key}),
        )
    except Exception as exc:
        log.warning("market.twelvedata.fetch_quotes failed: %s", safe_err(exc))
        return {}

    # Twelve Data returns the quote dict directly when a SINGLE symbol is requested
    # (the top-level object contains a "symbol" string key), and a symbol-keyed mapping
    # when multiple symbols are requested.
    if "symbol" in body:
        # Single-symbol response — the body IS the quote object.
        sym = body.get("symbol", symbols[0]).upper()
        return {sym: _normalize_quote(body)}

    # Multi-symbol response — each value is a quote object.
    result: dict[str, dict] = {}
    for sym, quote_raw in body.items():
        if not isinstance(quote_raw, dict):
            continue
        result[sym.upper()] = _normalize_quote(quote_raw)
    return result


def fetch_time_series(
    symbol: str,
    *,
    interval: str = "1day",
    outputsize: int = 60,
) -> list[dict]:
    """Fetch OHLC bars for `symbol` and persist them to OHLCBar.

    `interval` must be one of the Twelve Data interval strings (e.g. "1day", "1h",
    "15min"). Returns a BARS CONTRACT list (oldest→newest). Returns [] on any failure.
    Never raises.

    The returned bars are also written to OHLCBar using the corresponding OUR timeframe
    code (e.g. "1d" for "1day") via an idempotent upsert.
    """
    from apps.core.mocks import is_mock_mode

    if is_mock_mode():
        our_tf = _TD_TO_TF.get(interval, "1d")
        bars = _canned_time_series(symbol)
        _persist_bars(symbol.upper(), our_tf, bars)
        return bars

    api_key = _api_key()
    if not api_key:
        log.info("market.twelvedata: no credential configured, skipping fetch_time_series")
        return []

    sym = symbol.upper()
    our_tf = _TD_TO_TF.get(interval, "1d")
    cache_key = f"market:twelvedata:ts:{sym}:{interval}:{outputsize}"

    try:
        body = cache.get_or_fetch(
            cache_key,
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{our_tf}"),
            fetcher=lambda: _get(
                "/time_series",
                {
                    "symbol": sym,
                    "interval": interval,
                    "outputsize": outputsize,
                    "order": "ASC",
                    "apikey": api_key,
                },
            ),
        )
    except Exception as exc:
        log.warning(
            "market.twelvedata.fetch_time_series failed %s/%s: %s", sym, interval, safe_err(exc)
        )
        return []

    values = body.get("values") if isinstance(body, dict) else None
    if not isinstance(values, list):
        return []

    bars: list[dict] = []
    for raw in values:
        bar = _normalize_bar(raw)
        if bar is not None:
            bars.append(bar)

    _persist_bars(sym, our_tf, bars)
    return bars
