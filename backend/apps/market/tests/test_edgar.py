"""Tests for the SEC EDGAR service (edgar.py).

All tests are pure unit tests — no DB, no Redis. The _get helper and
cache.get_or_fetch are patched so nothing leaves the process.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import apps.market.services.edgar as edgar_mod
from apps.market.services.edgar import fetch_filings, fetch_insider

# ---------------------------------------------------------------------------
# Shared raw-response fixtures
# ---------------------------------------------------------------------------

_TICKER_MAP_RAW: dict = {
    "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
    "1": {"cik_str": 789019, "ticker": "MSFT", "title": "Microsoft Corporation"},
}

_APPLE_CIK = 320193


def _days_ago(n: int) -> str:
    return (datetime.now(UTC) - timedelta(days=n)).date().isoformat()


# Dynamic dates keep the fixture inside fetch_filings' recency window forever
# (literal dates would silently age past the ~18-month cutoff).
_FILED = [
    _days_ago(30),
    _days_ago(60),
    _days_ago(90),
    _days_ago(120),
    _days_ago(150),
    _days_ago(180),
]

_SUBMISSIONS_RAW: dict = {
    "name": "Apple Inc.",
    "filings": {
        "recent": {
            "form": ["10-K", "10-Q", "8-K", "4", "10-Q", "4"],
            "filingDate": list(_FILED),
            "accessionNumber": [
                "0000320193-25-000001",
                "0000320193-25-000002",
                "0000320193-25-000003",
                "0000320193-25-000004",
                "0000320193-25-000005",
                "0000320193-25-000006",
            ],
            "primaryDocument": [
                "form10k.htm",
                "form10q.htm",
                "form8k.htm",
                "form4.xml",
                "form10q_q2.htm",
                "form4_apr.xml",
            ],
            "reportDate": [
                "2025-09-30",
                "2025-06-30",
                "",
                "",
                "2025-03-31",
                "",
            ],
        }
    },
}


def _get_side_effect(url: str, *, headers: dict) -> dict:
    """Return the appropriate fixture depending on which EDGAR endpoint is called."""
    if "company_tickers" in url:
        return _TICKER_MAP_RAW
    if "submissions" in url:
        return _SUBMISSIONS_RAW
    return {}


def _passthrough_cache(key: str, *, ttl_seconds: int, fetcher):
    return fetcher()


# ---------------------------------------------------------------------------
# fetch_filings — normalized output + form filtering + URL construction
# ---------------------------------------------------------------------------


def test_fetch_filings_returns_normalized_list():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("AAPL")

    assert isinstance(result, list)
    assert len(result) > 0

    first = result[0]
    assert first["form"] == "10-K"
    assert first["filed"] == _FILED[0]
    assert first["report_date"] == "2025-09-30"
    assert first["accession"] == "0000320193-25-000001"
    assert first["title"] == "Apple Inc. 10-K"
    # URL uses accession with dashes removed
    assert "000032019325000001" in first["url"]
    assert "form10k.htm" in first["url"]
    assert str(_APPLE_CIK) in first["url"]


def test_fetch_filings_form_filtering():
    """When forms=('10-K',) only 10-K rows appear in the result."""
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("AAPL", forms=("10-K",))

    assert all(f["form"] == "10-K" for f in result)
    assert len(result) == 1


def test_fetch_filings_includes_10q_and_8k_by_default():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("AAPL")

    forms_present = {f["form"] for f in result}
    assert "10-K" in forms_present
    assert "10-Q" in forms_present
    assert "8-K" in forms_present
    # Form 4 not in default forms
    assert "4" not in forms_present


def test_fetch_filings_newest_first():
    """Filings returned in newest-first order (EDGAR returns most-recent first already)."""
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("AAPL")

    filed_dates = [f["filed"] for f in result]
    assert filed_dates == sorted(filed_dates, reverse=True)


def test_fetch_filings_respects_limit():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("AAPL", limit=2)

    assert len(result) <= 2


def test_fetch_filings_url_construction():
    """accessionNumber dashes must be stripped for the archive URL."""
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("AAPL", forms=("10-K",))

    assert len(result) == 1
    url = result[0]["url"]
    # Dashes removed from accession in URL path
    assert "-" not in url.split("/Archives/edgar/data/")[-1].split("/")[1]
    assert url.startswith("https://www.sec.gov/Archives/edgar/data/")


# ---------------------------------------------------------------------------
# fetch_insider — Form 4 filtering
# ---------------------------------------------------------------------------


def test_fetch_insider_returns_form4_only():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_insider("AAPL")

    assert isinstance(result, list)
    assert len(result) == 2  # two form 4s in the fixture
    for item in result:
        assert "filed" in item
        assert "accession" in item
        assert "url" in item
        assert item["title"] == "Apple Inc. Form 4"


def test_fetch_insider_url_contains_cik_and_nodash():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_insider("AAPL")

    assert len(result) > 0
    url = result[0]["url"]
    assert str(_APPLE_CIK) in url
    # Accession number without dashes must appear in the URL
    expected_nodash = "000032019325000004"
    assert expected_nodash in url


def test_fetch_insider_respects_limit():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_insider("AAPL", limit=1)

    assert len(result) <= 1


# ---------------------------------------------------------------------------
# Mock mode
# ---------------------------------------------------------------------------


def test_fetch_filings_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = fetch_filings("AAPL")

    assert isinstance(result, list)
    assert len(result) > 0
    first = result[0]
    assert "form" in first
    assert "filed" in first
    assert "report_date" in first
    assert "accession" in first
    assert "title" in first
    assert "url" in first
    assert first["form"] in ("10-K", "10-Q", "8-K")


def test_fetch_filings_mock_mode_respects_form_filter():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = fetch_filings("AAPL", forms=("10-K",))

    assert all(f["form"] == "10-K" for f in result)


def test_fetch_insider_mock_mode_returns_canned():
    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        result = fetch_insider("TSLA")

    assert isinstance(result, list)
    assert len(result) > 0
    first = result[0]
    assert "filed" in first
    assert "accession" in first
    assert "url" in first
    assert "title" in first
    assert "Form 4" in first["title"]


# ---------------------------------------------------------------------------
# Unknown ticker
# ---------------------------------------------------------------------------


def test_fetch_filings_and_insider_drop_stale_entries_by_default():
    """A rarely-filing issuer (the audit's QQQ trust served 8-Ks from 2014) must
    not surface decade-old documents as current context."""
    from datetime import UTC, datetime, timedelta

    fresh = (datetime.now(UTC) - timedelta(days=30)).date().isoformat()
    submissions = {
        "name": "Invesco QQQ Trust",
        "filings": {
            "recent": {
                "form": ["8-K", "8-K", "4", "4"],
                "filingDate": [fresh, "2014-09-08", fresh, "2014-02-07"],
                "accessionNumber": ["0-1", "0-2", "0-3", "0-4"],
                "primaryDocument": ["a.htm", "b.htm", "c.xml", "d.xml"],
                "reportDate": ["", "", "", ""],
            }
        },
    }

    def _side_effect(url: str, *, headers: dict) -> dict:
        if "company_tickers" in url:
            return {"0": {"cik_str": 1067839, "ticker": "QQQ", "title": "Invesco QQQ Trust"}}
        return submissions

    with (
        patch("apps.market.services.edgar._get", side_effect=_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        filings = fetch_filings("QQQ")
        insider = fetch_insider("QQQ")

    assert [f["filed"] for f in filings] == [fresh]
    assert [f["filed"] for f in insider] == [fresh]
    # Futures roots and cash indices are not SEC filers — no EDGAR round-trip.
    with (
        patch("apps.market.services.edgar._get") as fake_get,
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        assert fetch_filings("NQ") == []
        assert fetch_filings("/ES") == []
        assert fetch_insider("$SPX") == []
    fake_get.assert_not_called()


def test_fetch_filings_unknown_ticker_returns_empty():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("ZZZZZ_DOES_NOT_EXIST")

    assert result == []


def test_fetch_insider_unknown_ticker_returns_empty():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_insider("ZZZZZ_DOES_NOT_EXIST")

    assert result == []


# ---------------------------------------------------------------------------
# Network failures — never raises
# ---------------------------------------------------------------------------


def test_fetch_filings_never_raises_on_network_error():
    def _boom(url: str, *, headers: dict) -> dict:
        raise RuntimeError("connection refused")

    with (
        patch("apps.market.services.edgar._get", side_effect=_boom),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("AAPL")

    assert result == []


def test_fetch_insider_never_raises_on_network_error():
    def _boom(url: str, *, headers: dict) -> dict:
        raise RuntimeError("connection refused")

    with (
        patch("apps.market.services.edgar._get", side_effect=_boom),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_insider("AAPL")

    assert result == []


def test_fetch_filings_never_raises_on_submissions_error():
    """Ticker map succeeds but submissions fetch fails → []."""

    def _partial_fail(url: str, *, headers: dict) -> dict:
        if "company_tickers" in url:
            return _TICKER_MAP_RAW
        raise OSError("submissions unreachable")

    with (
        patch("apps.market.services.edgar._get", side_effect=_partial_fail),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_filings("AAPL")

    assert result == []


def test_fetch_insider_never_raises_on_submissions_error():
    def _partial_fail(url: str, *, headers: dict) -> dict:
        if "company_tickers" in url:
            return _TICKER_MAP_RAW
        raise OSError("submissions unreachable")

    with (
        patch("apps.market.services.edgar._get", side_effect=_partial_fail),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result = fetch_insider("AAPL")

    assert result == []


# ---------------------------------------------------------------------------
# Ticker normalisation (case-insensitive)
# ---------------------------------------------------------------------------


def test_fetch_filings_case_insensitive_ticker():
    with (
        patch("apps.market.services.edgar._get", side_effect=_get_side_effect),
        patch(
            "apps.market.services.edgar.cache.get_or_fetch",
            side_effect=_passthrough_cache,
        ),
    ):
        result_lower = fetch_filings("aapl")
        result_upper = fetch_filings("AAPL")

    assert len(result_lower) == len(result_upper)


# ---------------------------------------------------------------------------
# _get helper — uses full URL, sends required headers
# ---------------------------------------------------------------------------


def test_get_helper_sends_user_agent(monkeypatch):
    """_get must include User-Agent and Accept-Encoding in every request."""
    import requests

    captured_headers: dict = {}

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {}

    def _fake_get(url, *, headers, timeout):
        captured_headers.update(headers)
        return _FakeResp()

    monkeypatch.setattr(requests, "get", _fake_get)
    edgar_mod._get("https://www.sec.gov/files/company_tickers.json", headers=_headers())

    assert "User-Agent" in captured_headers
    assert "Accept-Encoding" in captured_headers


def _headers():
    """Local helper mirror of the module-level _headers() for tests."""
    return edgar_mod._headers()
