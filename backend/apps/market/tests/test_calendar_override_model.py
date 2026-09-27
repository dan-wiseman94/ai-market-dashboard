import pytest
from django.db import IntegrityError

from apps.market.models import CalendarOverride


@pytest.mark.django_db
def test_symbol_is_unique():
    CalendarOverride.objects.create(symbol="SPY", market_key="us_equity")
    with pytest.raises(IntegrityError):
        CalendarOverride.objects.create(symbol="SPY", market_key="crypto")
