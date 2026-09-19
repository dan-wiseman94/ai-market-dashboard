"""TradingView (official MCP server) as a market-data provider.

Normalizes TradingView tool results to the app's QUOTES / BARS / NEWS contracts so
``fallback.py`` routes to it exactly like the free providers (it sits FIRST among the
fallbacks). TradingView symbols are ``EXCHANGE:TICKER``; ``to_tv_symbol`` maps the app's
Schwab-style spellings (``$VIX``, ``/ES``) through a table and resolves equities via
``search_symbols`` (cached 7 days). Every fetcher returns empty on any failure, and
``is_connected`` treats a provider_health auth-error marker as "not connected" so a
rejected token stops costing a failing round trip per call. Result key spellings are
handled leniently — the live shapes are confirmed against the captured fixture (spec §9).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.market import cache
from apps.market.services import tradingview_mcp as mcp
from apps.market.services._bars import persist_bars
from apps.market.services.safe_log import safe_err
from apps.market.symbols import normalize_symbol
from apps.secrets.tradingview_oauth import load_token

log = logging.getLogger(__name__)

PROVIDER = "tradingview"
TV_NEWS_BASE = "https://www.tradingview.com"

# App spelling -> TradingView symbol. None = no TradingView equivalent (breadth internals).
INDEX_SYMBOLS: dict[str, str | None] = {
    "$VIX": "TVC:VIX",
    "$SPX": "SP:SPX",
    "$NDX": "NASDAQ:NDX",
    "$DJI": "DJ:DJI",
    "$RUT": "TVC:RUT",
    "$TNX": "TVC:TNX",
    "$COMPX": "NASDAQ:IXIC",
    "$OEX": "SP:OEX",
    "$ADVN": None,
    "$DECN": None,
    "$TICK": None,
    "$TRIN": None,
}
FUTURE_SYMBOLS: dict[str, str] = {
    "/ES": "CME_MINI:ES1!",
    "/NQ": "CME_MINI:NQ1!",
    "/RTY": "CME_MINI:RTY1!",
    "/YM": "CBOT_MINI:YM1!",
    "/CL": "NYMEX:CL1!",
    "/GC": "COMEX:GC1!",
    "/SI": "COMEX:SI1!",
    "/ZB": "CBOT:ZB1!",
    "/ZN": "CBOT:ZN1!",
    "/ZF": "CBOT:ZF1!",
    "/NG": "NYMEX:NG1!",
    "/HG": "COMEX:HG1!",
    "/VX": "CFE:VX1!",
    "/6E": "CME:6E1!",
}
_US_EXCHANGES = ("NASDAQ", "NYSE", "AMEX", "CBOE", "ARCA", "BATS")
_INTERVALS = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "1d": "1D"}
_SYMBOL_CACHE_TTL = 7 * 86_400
_QUOTE_COLUMNS = ["close", "change", "volume", "high", "low"]
_MAX_NEWS_TICKERS = 5


def is_connected() -> bool:
    """A usable token exists, no auth-error marker is set, and the 60s rate-limit
    marker (set on HTTP 429) isn't — both are circuit breakers."""
    from apps.core import provider_health

    return (
        load_token() is not None
        and provider_health.auth_error(PROVIDER) is None
        and not mcp.is_rate_limited()
    )


# --- lenient result helpers (shared with the calendar normalizers) ----------------------


def _rows(result: Any, *keys: str) -> list[dict]:
    """A list of dict rows from a tool result that is either a list or a dict holding one."""
    if isinstance(result, list):
        return [r for r in result if isinstance(r, dict)]
    if isinstance(result, dict):
        for key in keys:
            value = result.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def _first(row: dict, *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


# --- symbols ---------------------------------------------------------------------------


def _full_symbol(hit: dict) -> str | None:
    symbol = str(hit.get("symbol") or "")
    if ":" in symbol:
        return symbol
    exchange = str(hit.get("exchange") or "")
    ticker = str(_first(hit, "ticker", "name") or symbol)
    return f"{exchange}:{ticker}" if exchange and ticker else None


def _pick(hits: list[dict], ticker: str) -> str | None:
    """The hit whose ticker equals ``ticker``, preferring US exchanges."""
    matches = [
        h
        for h in hits
        if str(_first(h, "ticker", "name", "symbol") or "").upper().split(":")[-1] == ticker
    ]
    for exchange in _US_EXCHANGES:
        for hit in matches:
            if str(hit.get("exchange") or "").upper() == exchange:
                return _full_symbol(hit)
    return _full_symbol(matches[0]) if matches else None


def _search(ticker: str, type_filter: str) -> str | None:
    result = mcp.call_tool("search_symbols", {"query": ticker, "type_filter": type_filter})
    return _pick(_rows(result, "symbols", "results", "data", "items"), ticker)


def to_tv_symbol(ticker: str) -> str | None:
    """TradingView ``EXCHANGE:TICKER`` for an app ticker, or None when unmappable."""
    t = normalize_symbol(ticker)
    if not t:
        return None
    if t.startswith("$"):
        return INDEX_SYMBOLS.get(t)
    if t.startswith("/"):
        return FUTURE_SYMBOLS.get(t)
    try:
        # cache.get_or_fetch DOES cache a None result (JSON null reads back as a hit
        # returning None) — the "" sentinel exists because str(None) or None below
        # would yield the string "None".
        resolved: Any = cache.get_or_fetch(
            f"tradingview:symbol:{t}",
            ttl_seconds=_SYMBOL_CACHE_TTL,
            fetcher=lambda: _search(t, "stock") or _search(t, "etf") or "",
        )
    except Exception as exc:
        log.warning("tradingview.symbol_resolve_failed ticker=%s: %s", t, safe_err(exc))
        return None
    return str(resolved) or None


# --- bars ------------------------------------------------------------------------------


def _normalize_bar(raw: dict) -> dict | None:
    t = _float(_first(raw, "t", "time", "timestamp"))
    if t is None:
        return None
    if t > 1e11:  # milliseconds
        t /= 1000
    open_ = _float(_first(raw, "o", "open"))
    high = _float(_first(raw, "h", "high"))
    low = _float(_first(raw, "l", "low"))
    close = _float(_first(raw, "c", "close"))
    volume = _int(_first(raw, "v", "volume"))
    if None in (open_, high, low, close, volume):
        return None
    ts = datetime.fromtimestamp(int(t), tz=UTC).isoformat()
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume, "ts": ts}


def _fetch_bars_uncached(
    ticker: str, symbol: str, timeframe: str, interval: str, limit: int
) -> list[dict]:
    result = mcp.call_tool(
        "get_ohlcv", {"symbol": symbol, "interval": interval, "count": int(limit), "summary": False}
    )
    bars = [
        b
        for b in (_normalize_bar(r) for r in _rows(result, "bars", "data", "candles", "ohlcv"))
        if b
    ]
    bars.sort(key=lambda b: b["ts"])
    bars = bars[-int(limit) :]
    persist_bars(ticker, timeframe, bars, source=PROVIDER)
    return bars


def fetch_bars(ticker: str, *, timeframe: str = "1d", limit: int = 60) -> list[dict]:
    """BARS CONTRACT rows (oldest first), persisted to OHLCBar. [] on any failure."""
    interval = _INTERVALS.get(timeframe)
    symbol = to_tv_symbol(ticker)
    if interval is None or symbol is None:
        return []
    t = normalize_symbol(ticker)
    try:
        bars: list[dict] = cache.get_or_fetch(
            f"tradingview:ohlc:{t}:{timeframe}:{limit}",
            ttl_seconds=cache.ttl_for_kind(f"ohlc_{timeframe}"),
            fetcher=lambda: _fetch_bars_uncached(t, symbol, timeframe, interval, limit),
        )
        return bars
    except Exception as exc:
        log.warning("tradingview.bars_failed ticker=%s: %s", t, safe_err(exc))
        return []


# --- quotes ----------------------------------------------------------------------------


def _batch_rows(result: Any) -> dict[str, dict]:
    """``{symbol: row}`` from a batch result, accepting either flat rows or the scanner
    ``{"s": symbol, "d": [values in column order]}`` shape."""
    columns = result.get("columns") if isinstance(result, dict) else None
    out: dict[str, dict] = {}
    for row in _rows(result, "data", "symbols", "results", "rows", "items"):
        if "d" in row and isinstance(row.get("d"), list):
            names = columns if isinstance(columns, list) else _QUOTE_COLUMNS
            # Coerce each column entry to a string name — the scanner can send column
            # descriptors as {"name": "close", ...} instead of a bare "close" string.
            names = [str(c.get("name", c)) if isinstance(c, dict) else str(c) for c in names]
            flat = dict(zip(names, row["d"], strict=False))
            out[str(_first(row, "s", "symbol") or "")] = flat
        else:
            out[str(_first(row, "symbol", "name", "s") or "")] = row
    return out


def fetch_quotes(tickers: list[str]) -> dict[str, dict]:
    """QUOTES CONTRACT keyed by the app's ticker spelling. {} on any failure."""
    mapping = {normalize_symbol(t): to_tv_symbol(t) for t in tickers if t}
    symbols = [s for s in mapping.values() if s]
    if not symbols:
        return {}
    try:
        result = mcp.call_tool(
            "get_symbol_data_batch", {"symbols": symbols, "columns": _QUOTE_COLUMNS}
        )
        by_symbol = _batch_rows(result)
        out: dict[str, dict] = {}
        for ticker, symbol in mapping.items():
            row = by_symbol.get(symbol or "")
            if row is None:
                continue
            out[ticker] = {
                "last": _float(row.get("close")),
                "bid": None,
                "ask": None,
                "volume": _int(row.get("volume")),
                "high": _float(row.get("high")),
                "low": _float(row.get("low")),
                "pct_change": _float(row.get("change")),
            }
        return out
    except Exception as exc:
        log.warning("tradingview.quotes_failed: %s", safe_err(exc))
        return {}


# --- news ------------------------------------------------------------------------------


def _normalize_news(raw: dict, ticker: str) -> dict | None:
    external_id = _first(raw, "id", "uuid", "story_id")
    headline = str(_first(raw, "title", "headline") or "").strip()
    published = _int(_first(raw, "published", "published_at", "datetime", "timestamp"))
    if external_id is None or not headline or published is None:
        return None
    if published > 1e11:
        published //= 1000
    try:
        published_at = datetime.fromtimestamp(published, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        # Out-of-range epoch (e.g. a bogus huge int the ms heuristic doesn't tame) —
        # drop the item, same as a malformed bar.
        return None
    url = str(raw.get("link") or raw.get("url") or "")
    if not url and raw.get("storyPath"):
        url = f"{TV_NEWS_BASE}{raw['storyPath']}"
    ext_id = str(external_id)
    if len(ext_id) > 64:
        # NewsItem.external_id is max_length=64 — hash an overlong upstream id down to
        # a deterministic, fits-in-the-column value rather than dropping the item.
        ext_id = "h:" + hashlib.sha256(ext_id.encode()).hexdigest()[:40]
    return {
        "id": ext_id,
        "external_id": ext_id,
        "headline": headline[:512],
        "summary": str(raw.get("summary") or raw.get("description") or ""),
        "url": url[:1024],
        "source": str(_first(raw, "provider", "source") or "")[:64],
        "datetime": published,
        "published_at": published_at,
        "ticker": ticker,
        "related": ticker,
        "tickers": [ticker],
        "sentiment": {},
    }


def fetch_news(tickers: list[str], *, limit: int = 15) -> list[dict]:
    """Newest-first headlines for up to five tickers, deduped, upserted as NewsItem rows.

    Never raises: a malformed item is skipped and a persistence failure still returns
    the normalized headlines (best-effort persistence, never-raise fetch).
    """
    from apps.market.services.news import _upsert_items

    items: list[dict] = []
    for raw_ticker in [t for t in tickers if t][:_MAX_NEWS_TICKERS]:
        ticker = normalize_symbol(raw_ticker)
        symbol = to_tv_symbol(ticker)
        if symbol is None:
            continue
        try:
            result = mcp.call_tool("get_news", {"symbol": symbol, "limit": int(limit)})
        except Exception as exc:
            log.warning("tradingview.news_failed ticker=%s: %s", ticker, safe_err(exc))
            continue
        for raw in _rows(result, "items", "news", "data", "results"):
            try:
                item = _normalize_news(raw, ticker)
            except Exception as exc:
                log.warning(
                    "tradingview.news_normalize_failed ticker=%s: %s", ticker, safe_err(exc)
                )
                continue
            if item:
                items.append(item)
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in sorted(items, key=lambda i: i["datetime"], reverse=True):
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        deduped.append(item)
    deduped = deduped[:limit]
    try:
        _upsert_items(PROVIDER, deduped)
    except Exception as exc:
        log.warning("tradingview.news_persist_failed: %s", safe_err(exc))
    return deduped


# --- calendars -------------------------------------------------------------------------

_BMO = ("bmo", "before", "pre")
_AMC = ("amc", "after", "post")


def _date_str(value: Any) -> str | None:
    """'YYYY-MM-DD' from a date string, an ISO datetime, or a unix timestamp; else None."""
    if value is None:
        return None
    if isinstance(value, int | float):
        ts = float(value) / 1000 if value > 1e11 else float(value)
        return datetime.fromtimestamp(ts, tz=UTC).date().isoformat()
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _session_hint(value: Any) -> str:
    text = str(value or "").lower()
    if any(k in text for k in _BMO):
        return "bmo"
    if any(k in text for k in _AMC):
        return "amc"
    return ""


def _iso_datetime(value: Any) -> str | None:
    """Timezone-aware ISO string from an ISO string or unix timestamp; else None."""
    if value is None:
        return None
    if isinstance(value, int | float):
        ts = float(value) / 1000 if value > 1e11 else float(value)
        return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


def fetch_earnings(tickers: list[str]) -> list[dict]:
    """Rows in the shape ``events._upsert_earnings`` consumes. [] on any failure."""
    mapping = {normalize_symbol(t): to_tv_symbol(t) for t in tickers if t}
    symbols = [s for s in mapping.values() if s]
    if not symbols:
        return []
    try:
        result = mcp.call_tool("get_earnings_calendar", {"symbols": symbols})
    except Exception as exc:
        log.warning("tradingview.earnings_failed: %s", safe_err(exc))
        return []
    back = {s: t for t, s in mapping.items() if s}
    rows: list[dict] = []
    for raw in _rows(result, "events", "earnings", "data", "results", "items"):
        try:
            symbol = str(_first(raw, "symbol", "name") or "")
            ticker = back.get(symbol) or symbol.split(":")[-1]
            date = _date_str(
                _first(raw, "date", "earnings_release_date", "timestamp")
            ) or _date_str(raw.get("time"))
            if not ticker or not date:
                continue
            rows.append(
                {
                    "symbol": ticker,
                    "date": date,
                    "hour": _session_hint(_first(raw, "time", "session", "hour", "release_time")),
                    "epsEstimate": _float(
                        _first(raw, "eps_estimate", "epsEstimate", "eps_forecast")
                    ),
                    "revenueEstimate": _float(
                        _first(raw, "revenue_estimate", "revenueEstimate", "revenue_forecast")
                    ),
                }
            )
        except Exception as exc:
            log.warning("tradingview.earnings_row_failed: %s", safe_err(exc))
            continue
    return rows


def fetch_economic_calendar(*, ahead_days: int = 45) -> list[dict]:
    """US macro rows in the shape ``events._upsert_macro`` consumes. [] on any failure."""
    today = datetime.now(UTC).date()
    end = today + timedelta(days=ahead_days)
    try:
        result = mcp.call_tool(
            "get_economic_calendar",
            {"countries": ["US"], "from_date": today.isoformat(), "to_date": end.isoformat()},
        )
    except Exception as exc:
        log.warning("tradingview.macro_failed: %s", safe_err(exc))
        return []
    rows: list[dict] = []
    for raw in _rows(result, "events", "data", "results", "items"):
        try:
            when = _iso_datetime(_first(raw, "date", "time", "timestamp", "datetime"))
            if when is None:
                continue
            rows.append(
                {
                    "event": str(_first(raw, "title", "event", "name") or ""),
                    "impact": str(_first(raw, "importance", "impact") or ""),
                    "country": str(_first(raw, "country", "country_code") or "US"),
                    "time": when,
                    "estimate": _float(_first(raw, "forecast", "estimate", "consensus")),
                    "prev": _float(_first(raw, "previous", "prev", "prior")),
                    "actual": _float(raw.get("actual")),
                }
            )
        except Exception as exc:
            log.warning("tradingview.macro_row_failed: %s", safe_err(exc))
            continue
    return rows
