from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.market.models import MarketEvent


@pytest.mark.django_db
def test_market_event_dedups_on_source_external_id():
    now = timezone.now()
    MarketEvent.objects.create(
        source="finnhub",
        external_id="EARN:NVDA:2026-05-28",
        kind="earnings",
        ticker="NVDA",
        title="NVDA earnings",
        event_time=now + timedelta(days=2),
    )
    with pytest.raises(IntegrityError):
        MarketEvent.objects.create(
            source="finnhub",
            external_id="EARN:NVDA:2026-05-28",
            kind="earnings",
            ticker="NVDA",
            title="dup",
            event_time=now + timedelta(days=2),
        )


@pytest.mark.django_db
def test_market_event_orders_by_event_time():
    now = timezone.now()
    MarketEvent.objects.create(
        source="s", external_id="b", kind="cpi", title="CPI", event_time=now + timedelta(days=5)
    )
    MarketEvent.objects.create(
        source="s", external_id="a", kind="fomc", title="FOMC", event_time=now + timedelta(days=1)
    )
    titles = list(MarketEvent.objects.order_by("event_time").values_list("title", flat=True))
    assert titles == ["FOMC", "CPI"]
