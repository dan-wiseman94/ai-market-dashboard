from datetime import date, timedelta
from unittest.mock import patch

import pytest

from apps.market.models import CorporateAction
from apps.snapshots.services import _fetch_events_section


@pytest.mark.django_db
def test_fetch_events_section_includes_future_corporate_action():
    ex_date = date.today() + timedelta(days=5)
    CorporateAction.objects.create(
        source="mock",
        external_id="DIV:AAPL:1",
        kind="dividend",
        ticker="AAPL",
        ex_date=ex_date,
        amount=0.26,
    )
    with patch(
        "apps.snapshots.services.upcoming_events",
        return_value={"earnings": [], "macro": []},
    ) as m:
        out = _fetch_events_section(watchlist_tickers=["aapl"])
    m.assert_called_once_with(["aapl"], within_days=14, include_macro=True)
    assert out["data"]["corporate_actions"] == [
        {
            "ticker": "AAPL",
            "kind": "dividend",
            "ex_date": ex_date.isoformat(),
            "ratio": None,
            "amount": 0.26,
        }
    ]


@pytest.mark.django_db
def test_fetch_events_section_excludes_out_of_window_and_other_tickers():
    CorporateAction.objects.create(
        source="mock",
        external_id="DIV:AAPL:2",
        kind="dividend",
        ticker="AAPL",
        ex_date=date.today() + timedelta(days=20),  # outside the 14-day window
        amount=0.26,
    )
    CorporateAction.objects.create(
        source="mock",
        external_id="SPLIT:MSFT:1",
        kind="split",
        ticker="MSFT",  # not in watchlist
        ex_date=date.today() + timedelta(days=3),
        ratio=2.0,
    )
    with patch(
        "apps.snapshots.services.upcoming_events",
        return_value={"earnings": [], "macro": []},
    ):
        out = _fetch_events_section(watchlist_tickers=["AAPL"])
    assert out["data"]["corporate_actions"] == []


@pytest.mark.django_db
def test_fetch_events_section_caps_at_twenty_rows():
    for i in range(25):
        CorporateAction.objects.create(
            source="mock",
            external_id=f"DIV:AAPL:{i}",
            kind="dividend",
            ticker="AAPL",
            ex_date=date.today() + timedelta(days=i % 14),
            amount=0.1,
        )
    with patch(
        "apps.snapshots.services.upcoming_events",
        return_value={"earnings": [], "macro": []},
    ):
        out = _fetch_events_section(watchlist_tickers=["AAPL"])
    assert len(out["data"]["corporate_actions"]) == 20
