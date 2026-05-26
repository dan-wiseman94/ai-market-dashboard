import pytest

from apps.market.calendar.resolve import calendar_for, clear_resolution_cache
from apps.market.models import CalendarOverride


@pytest.mark.django_db
def test_override_beats_heuristic():
    clear_resolution_cache()
    assert calendar_for("SPY") == "us_equity"  # heuristic
    CalendarOverride.objects.create(symbol="SPY", market_key="crypto")  # save() clears cache
    assert calendar_for("SPY") == "crypto"


@pytest.mark.django_db
def test_deleting_override_reverts_to_heuristic():
    o = CalendarOverride.objects.create(symbol="FOO", market_key="crypto")
    assert calendar_for("FOO") == "crypto"
    o.delete()  # clears cache
    assert calendar_for("FOO") == "us_equity"
