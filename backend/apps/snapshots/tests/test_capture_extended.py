from unittest.mock import patch

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture


@pytest.mark.django_db
def test_capture_chain_uses_first_chain_capable_symbol():
    # Schwab's chains endpoint 400s on futures symbols; a futures-primary
    # watchlist should get the chain of its first non-futures symbol instead.
    profile = TradingProfile.objects.create(name="P", style="x")
    fake_chain = {"ticker": "QQQ", "underlying_last": "703.70", "expiries": {}}

    with patch("apps.snapshots.services.fetch_chain", return_value=fake_chain) as fake:
        snap = capture(
            profile=profile,
            objective="",
            includes=["chain"],
            watchlist_tickers=["NQ", "QQQ"],
        )

    fake.assert_called_once_with("QQQ")
    assert snap.sections.get(kind="chain").status == "done"


@pytest.mark.django_db
def test_capture_chain_fails_clearly_when_watchlist_is_all_futures():
    profile = TradingProfile.objects.create(name="P", style="x")

    with patch("apps.snapshots.services.fetch_chain") as fake:
        snap = capture(
            profile=profile,
            objective="",
            includes=["chain"],
            watchlist_tickers=["NQ", "/ESU26"],
        )

    fake.assert_not_called()
    sec = snap.sections.get(kind="chain")
    assert sec.status == "failed"
    assert "futures" in sec.error
    assert "no chain-capable symbol" in sec.error


@pytest.mark.django_db
def test_capture_filings_skips_non_equity_watchlist_symbols():
    profile = TradingProfile.objects.create(name="P", style="x")

    with patch("apps.snapshots.services.edgar_fetch_filings", return_value=[]) as fake:
        snap = capture(
            profile=profile,
            objective="",
            includes=["filings"],
            watchlist_tickers=["NQ", "QQQ"],
        )

    assert fake.call_count == 2
    fake.assert_any_call("QQQ")
    fake.assert_any_call("QQQ", forms=("4",), limit=5, max_age_days=45)
    sec = snap.sections.get(kind="filings")
    assert sec.status == "done"
    assert list(sec.payload.keys()) == ["QQQ"]
    assert sec.payload["QQQ"] == {"filings": [], "insider": []}
