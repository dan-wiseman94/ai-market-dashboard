from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.market.models import MarketEvent
from apps.market.services.events import upcoming_events


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
def test_upcoming_events_returns_chronologically_ordered_macro():
    # Insertion order is deliberately non-chronological so a pk-ordered read
    # would fail — upcoming_events must sort by event_time.
    now = timezone.now()
    MarketEvent.objects.create(
        source="s", external_id="b", kind="cpi", title="CPI", event_time=now + timedelta(days=5)
    )
    MarketEvent.objects.create(
        source="s", external_id="a", kind="fomc", title="FOMC", event_time=now + timedelta(days=1)
    )
    MarketEvent.objects.create(
        source="s", external_id="c", kind="nfp", title="NFP", event_time=now + timedelta(days=3)
    )
    out = upcoming_events([], within_days=14)
    assert [m["title"] for m in out["macro"]] == ["FOMC", "NFP", "CPI"]
