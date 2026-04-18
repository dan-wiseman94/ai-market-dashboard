import pytest

from apps.market.models import OptionChainSnapshot


@pytest.mark.django_db
def test_optionchainsnapshot_persists_payload_and_expiries():
    row = OptionChainSnapshot.objects.create(
        ticker="SPY",
        expiries=["2026-04-25", "2026-05-16"],
        payload={
            "underlying_last": "521.30",
            "expiries": {"2026-04-25": {"calls": [], "puts": []}},
        },
    )
    fetched = OptionChainSnapshot.objects.get(id=row.id)
    assert fetched.ticker == "SPY"
    assert fetched.expiries == ["2026-04-25", "2026-05-16"]
    assert fetched.payload["underlying_last"] == "521.30"
    assert fetched.fetched_at is not None
