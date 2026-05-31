"""Catalog of connectable market-data providers for the settings GUI.

Drives ``GET/PUT/DELETE /api/schwab/data-sources/``. Each entry describes how a
provider authenticates so the frontend can render the right card:

- ``oauth``      — Schwab; connected via the existing OAuth flow (authorize/callback).
- ``key``        — a single API key in ``ApiCredential.token["api_key"]``.
- ``key_secret`` — key + secret (Alpaca) in ``ApiCredential.token``.
- ``none``       — keyless (SEC EDGAR, US Treasury); always available, nothing to store.

Credentials live encrypted in ``apps.secrets.ApiCredential``; this module is metadata
only and never holds a secret.
"""

from __future__ import annotations

# Order here is the order rendered in the settings UI.
DATA_SOURCES: list[dict] = [
    {
        "provider": "schwab",
        "label": "Charles Schwab",
        "auth": "oauth",
        "fields": [],
        "blurb": "Brokerage market data — quotes, OHLC, option chains, positions — via OAuth.",
        "docs_url": "https://developer.schwab.com",
    },
    {
        "provider": "alpaca",
        "label": "Alpaca",
        "auth": "key_secret",
        "fields": ["api_key", "api_secret"],
        "blurb": "Real-time IEX quotes + historical bars. Free with an API key + secret.",
        "docs_url": "https://alpaca.markets/",
    },
    {
        "provider": "finnhub",
        "label": "Finnhub",
        "auth": "key",
        "fields": ["api_key"],
        "blurb": "News, fundamentals, and the earnings/macro calendar. Free 60 req/min.",
        "docs_url": "https://finnhub.io/",
    },
    {
        "provider": "tiingo",
        "label": "Tiingo",
        "auth": "key",
        "fields": ["api_key"],
        "blurb": "30+ years of daily EOD bars, plus news. Free with an API key.",
        "docs_url": "https://www.tiingo.com/",
    },
    {
        "provider": "twelvedata",
        "label": "Twelve Data",
        "auth": "key",
        "fields": ["api_key"],
        "blurb": "Quotes, time-series, FX & crypto. Free 800 req/day.",
        "docs_url": "https://twelvedata.com/",
    },
    {
        "provider": "polygon",
        "label": "Polygon.io",
        "auth": "key",
        "fields": ["api_key"],
        "blurb": "End-of-day price history. Free 5 req/min, ~2-year lookback.",
        "docs_url": "https://polygon.io/",
    },
    {
        "provider": "tradier",
        "label": "Tradier",
        "auth": "key",
        "fields": ["api_key"],
        "blurb": "Delayed option chains via a free sandbox access token.",
        "docs_url": "https://documentation.tradier.com/",
    },
    {
        "provider": "fred",
        "label": "FRED (St. Louis Fed)",
        "auth": "key",
        "fields": ["api_key"],
        "blurb": "Macro indicators and the daily Treasury yield curve. Free API key.",
        "docs_url": "https://fred.stlouisfed.org/docs/api/api_key.html",
    },
    {
        "provider": "marketaux",
        "label": "Marketaux",
        "auth": "key",
        "fields": ["api_key"],
        "blurb": "Financial news with per-ticker sentiment. Free 100 req/day.",
        "docs_url": "https://www.marketaux.com/",
    },
    {
        "provider": "edgar",
        "label": "SEC EDGAR",
        "auth": "none",
        "fields": [],
        "blurb": "Company filings + Form 4 insider trades. No key required.",
        "docs_url": "https://www.sec.gov/edgar",
    },
    {
        "provider": "treasury",
        "label": "US Treasury",
        "auth": "none",
        "fields": [],
        "blurb": "FiscalData average rates + debt to the penny. No key required.",
        "docs_url": "https://fiscaldata.treasury.gov/",
    },
]

_BY_PROVIDER = {ds["provider"]: ds for ds in DATA_SOURCES}


def get_data_source(provider: str) -> dict | None:
    """Catalog entry for ``provider``, or None if it isn't a known data source."""
    return _BY_PROVIDER.get(provider)
