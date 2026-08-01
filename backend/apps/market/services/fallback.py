"""Free-provider fallbacks for when Schwab isn't connected.

The Schwab-backed services (quotes, ohlc, chain) call into here when
``get_schwab_client()`` / ``schwab_json`` raise ``SchwabNotConnectedError``
(which also covers ``SchwabAuthError`` — a rejected token). We pick the first
*configured* free provider — one with a credential (``ApiCredential`` row or an
.env-provided key) — in a fixed precedence and return the same normalized shape
as the Schwab path.

Each ``alt_*`` returns ``None`` when **no** provider is configured (so the caller
re-raises and the UI still says "connect Schwab"), and a real value — possibly
empty — when a provider is configured but returns nothing. This keeps the
"no Schwab + no alternative -> 503" contract intact while letting a user who has,
say, an Alpaca key run the whole dashboard without a brokerage login.

News is not Schwab-gated; ``alt_news`` is used by ``news.py`` only when Finnhub
has no key, to aggregate Marketaux / Tiingo instead.
"""

from __future__ import annotations

from apps.secrets.credentials import decrypt_token

# Our timeframe code -> Twelve Data interval string.
_TD_INTERVAL = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "1d": "1day"}


def _has(provider: str) -> bool:
    return decrypt_token(provider) is not None


def alt_quotes(tickers: list[str]) -> dict | None:
    """Quotes from the first configured provider (Alpaca -> Twelve Data), else None."""
    if _has("alpaca"):
        from apps.market.services import alpaca

        return alpaca.fetch_quotes(tickers)
    if _has("twelvedata"):
        from apps.market.services import twelvedata

        return twelvedata.fetch_quotes(tickers)
    return None


def alt_bars(ticker: str, timeframe: str, *, limit: int = 60) -> list | None:
    """Bars from the first configured provider, else None.

    Precedence: Alpaca (any timeframe) -> Twelve Data (any timeframe) ->
    Tiingo (daily only) -> Polygon (daily only). Intraday timeframes resolve only
    when Alpaca or Twelve Data is configured; daily-only providers return None
    for intraday requests.
    """
    if _has("alpaca"):
        from apps.market.services import alpaca

        return alpaca.fetch_bars(ticker, timeframe=timeframe, limit=limit)
    if _has("twelvedata"):
        from apps.market.services import twelvedata

        interval = _TD_INTERVAL.get(timeframe, "1day")
        return twelvedata.fetch_time_series(ticker, interval=interval, outputsize=limit)
    if timeframe == "1d" and _has("tiingo"):
        from apps.market.services import tiingo

        return tiingo.fetch_daily_bars(ticker, days=limit)
    if timeframe == "1d" and _has("polygon"):
        from apps.market.services import polygon

        return polygon.fetch_daily_bars(ticker, days=limit)
    return None


def alt_chain(ticker: str) -> dict | None:
    """Option chain from Tradier if configured, else None."""
    if _has("tradier"):
        from apps.market.services import tradier

        return tradier.fetch_chain(ticker)
    return None


def alt_news(tickers: list[str], *, limit: int = 15) -> list | None:
    """News from the first configured provider (Marketaux -> Tiingo), else None."""
    if _has("marketaux"):
        from apps.market.services import marketaux

        return marketaux.fetch_news(tickers, limit=limit)
    if _has("tiingo"):
        from apps.market.services import tiingo

        return tiingo.fetch_news(tickers, limit=limit)
    return None
