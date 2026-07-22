"""SEC EDGAR company filings + Form 4 insider transactions. No API key required.

Sourced from SEC EDGAR full-text search / data APIs (public, no auth):
- https://www.sec.gov/files/company_tickers.json   → ticker→CIK map (cached 24h)
- https://data.sec.gov/submissions/CIK##########.json → filing arrays per company

Caches ticker-map 24h (key "market:edgar:tickermap") and submissions per ticker
at filings TTL (default 3600s, registered by the parent). Both fetch functions
never raise — they return [] on any failure, including unknown ticker.

SEC fair-use is ~10 req/sec. A descriptive User-Agent is required per SEC policy;
configure via optional setting SEC_EDGAR_USER_AGENT (a safe default is baked in).
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime, timedelta

import requests  # type: ignore[import-untyped]
from django.conf import settings

from apps.market import cache
from apps.market.symbols import is_equity_like

log = logging.getLogger(__name__)

_TICKER_MAP_CACHE_KEY = "market:edgar:tickermap"
_TICKER_MAP_TTL = 86400  # 24h — changes rarely


def _ua() -> str:
    return getattr(settings, "SEC_EDGAR_USER_AGENT", "ai-dashboard research contact@example.com")


def _headers() -> dict[str, str]:
    return {"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"}


def _get(url: str, *, headers: dict) -> dict:
    """Fetch a FULL url (not path+base) and return a dict body."""
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


# ---------------------------------------------------------------------------
# Ticker → CIK map
# ---------------------------------------------------------------------------


def _load_ticker_map() -> dict[str, int]:
    """Return {TICKER_UPPER: cik_int} from EDGAR company_tickers.json (cached 24h)."""
    try:
        raw = cache.get_or_fetch(
            _TICKER_MAP_CACHE_KEY,
            ttl_seconds=_TICKER_MAP_TTL,
            fetcher=lambda: _get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=_headers(),
            ),
        )
    except Exception as exc:
        log.warning("market.edgar.ticker_map.fetch_failed: %s", exc)
        return {}

    # raw = {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    result: dict[str, int] = {}
    for entry in raw.values():
        if not isinstance(entry, dict):
            continue
        ticker = (entry.get("ticker") or "").upper()
        cik = entry.get("cik_str")
        if ticker and cik is not None:
            with contextlib.suppress(ValueError, TypeError):
                result[ticker] = int(cik)
    return result


def _cik_for(ticker: str) -> int | None:
    tmap = _load_ticker_map()
    return tmap.get(ticker.upper())


# ---------------------------------------------------------------------------
# Submissions fetch
# ---------------------------------------------------------------------------


def _fetch_submissions(ticker: str, cik: int) -> dict:
    """Fetch and cache the submissions JSON for a company by CIK."""
    padded = f"CIK{cik:010d}"
    url = f"https://data.sec.gov/submissions/{padded}.json"
    return cache.get_or_fetch(
        f"market:edgar:submissions:{ticker.upper()}",
        ttl_seconds=cache.ttl_for_kind("filings"),
        fetcher=lambda: _get(url, headers=_headers()),
    )


# ---------------------------------------------------------------------------
# Canned fixtures for MOCK_EXTERNAL / e2e mode
# ---------------------------------------------------------------------------


def _canned_filings(ticker: str) -> list[dict]:
    t = ticker.upper()
    name = f"{t} Corp"
    return [
        {
            "form": "10-K",
            "filed": "2025-11-01",
            "report_date": "2025-09-30",
            "accession": "0000000000-25-000001",
            "title": f"{name} 10-K",
            "url": "https://www.sec.gov/Archives/edgar/data/1/000000000025000001/form10k.htm",
        },
        {
            "form": "10-Q",
            "filed": "2025-08-05",
            "report_date": "2025-06-30",
            "accession": "0000000000-25-000002",
            "title": f"{name} 10-Q",
            "url": "https://www.sec.gov/Archives/edgar/data/1/000000000025000002/form10q.htm",
        },
        {
            "form": "8-K",
            "filed": "2025-07-15",
            "report_date": "",
            "accession": "0000000000-25-000003",
            "title": f"{name} 8-K",
            "url": "https://www.sec.gov/Archives/edgar/data/1/000000000025000003/form8k.htm",
        },
    ]


def _canned_insider(ticker: str) -> list[dict]:
    t = ticker.upper()
    name = f"{t} Corp"
    return [
        {
            "filed": "2025-10-20",
            "accession": "0000000000-25-000010",
            "url": "https://www.sec.gov/Archives/edgar/data/1/000000000025000010/form4.xml",
            "title": f"{name} Form 4",
        },
    ]


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------


def _build_filing_url(cik: int, accession: str, primary_doc: str) -> str:
    acc_nodash = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{primary_doc}"


def _min_filed(max_age_days: int) -> str:
    """ISO date floor for the recency filter (ISO strings compare lexicographically)."""
    return (datetime.now(UTC) - timedelta(days=max_age_days)).date().isoformat()


def _normalize_filings(
    company_name: str,
    cik: int,
    submissions: dict,
    *,
    forms: tuple[str, ...],
    limit: int,
    min_filed: str = "",
) -> list[dict]:
    """Extract and filter filings from a EDGAR submissions payload."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    form_list: list[str] = recent.get("form") or []
    filed_list: list[str] = recent.get("filingDate") or []
    acc_list: list[str] = recent.get("accessionNumber") or []
    doc_list: list[str] = recent.get("primaryDocument") or []
    report_list: list[str] = recent.get("reportDate") or []

    length = min(len(form_list), len(filed_list), len(acc_list), len(doc_list))
    # report_list may be shorter (not all forms carry a reportDate)
    report_padded = list(report_list) + [""] * length

    results: list[dict] = []
    for i in range(length):
        form = form_list[i]
        if form not in forms:
            continue
        if min_filed and filed_list[i] < min_filed:
            continue
        accession = acc_list[i]
        primary_doc = doc_list[i]
        url = _build_filing_url(cik, accession, primary_doc)
        results.append(
            {
                "form": form,
                "filed": filed_list[i],
                "report_date": report_padded[i] if i < len(report_padded) else "",
                "accession": accession,
                "title": f"{company_name} {form}",
                "url": url,
            }
        )
        if len(results) >= limit:
            break

    return results


def _normalize_insider(
    company_name: str,
    cik: int,
    submissions: dict,
    *,
    limit: int,
    min_filed: str = "",
) -> list[dict]:
    """Extract Form 4 filings from a EDGAR submissions payload."""
    recent = (submissions.get("filings") or {}).get("recent") or {}
    form_list: list[str] = recent.get("form") or []
    filed_list: list[str] = recent.get("filingDate") or []
    acc_list: list[str] = recent.get("accessionNumber") or []
    doc_list: list[str] = recent.get("primaryDocument") or []

    length = min(len(form_list), len(filed_list), len(acc_list), len(doc_list))

    results: list[dict] = []
    for i in range(length):
        if form_list[i] != "4":
            continue
        if min_filed and filed_list[i] < min_filed:
            continue
        accession = acc_list[i]
        primary_doc = doc_list[i]
        url = _build_filing_url(cik, accession, primary_doc)
        results.append(
            {
                "filed": filed_list[i],
                "accession": accession,
                "url": url,
                "title": f"{company_name} Form 4",
            }
        )
        if len(results) >= limit:
            break

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_filings(
    ticker: str,
    *,
    forms: tuple[str, ...] = ("10-K", "10-Q", "8-K"),
    limit: int = 10,
    max_age_days: int = 548,
) -> list[dict]:
    """Return the `limit` most-recent filings (newest-first) matching `forms`.

    Each item: {"form", "filed", "report_date", "accession", "title", "url"}.
    Filings older than `max_age_days` (default ~18 months — keeps the latest
    10-K cycle) are dropped: a rarely-filing issuer would otherwise surface
    decade-old documents as current context. Returns [] for an unknown ticker,
    credential-less fetch, or any network error. Never raises.
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()

    if is_mock_mode():
        return [f for f in _canned_filings(ticker) if f["form"] in forms][:limit]

    if not is_equity_like(ticker):
        return []  # futures roots / cash indices are not SEC filers

    cik = _cik_for(ticker)
    if cik is None:
        log.info("market.edgar.fetch_filings: unknown ticker %s", ticker)
        return []

    try:
        submissions = _fetch_submissions(ticker, cik)
    except Exception as exc:
        log.warning("market.edgar.fetch_filings.failed ticker=%s: %s", ticker, exc)
        return []

    company_name = submissions.get("name") or ticker
    return _normalize_filings(
        company_name,
        cik,
        submissions,
        forms=forms,
        limit=limit,
        min_filed=_min_filed(max_age_days),
    )


def fetch_insider(ticker: str, *, limit: int = 15, max_age_days: int = 548) -> list[dict]:
    """Return the `limit` most-recent Form 4 insider-transaction filings (newest-first).

    Each item: {"filed", "accession", "url", "title"}. Form 4s older than
    `max_age_days` are dropped (stale insider activity is noise, not signal).
    Returns [] for an unknown ticker or any network error. Never raises.
    """
    from apps.core.mocks import is_mock_mode

    ticker = ticker.upper()

    if is_mock_mode():
        return _canned_insider(ticker)[:limit]

    if not is_equity_like(ticker):
        return []  # futures roots / cash indices are not SEC filers

    cik = _cik_for(ticker)
    if cik is None:
        log.info("market.edgar.fetch_insider: unknown ticker %s", ticker)
        return []

    try:
        submissions = _fetch_submissions(ticker, cik)
    except Exception as exc:
        log.warning("market.edgar.fetch_insider.failed ticker=%s: %s", ticker, exc)
        return []

    company_name = submissions.get("name") or ticker
    return _normalize_insider(
        company_name, cik, submissions, limit=limit, min_filed=_min_filed(max_age_days)
    )
