import pytest

from apps.profiles.models import TradingProfile
from apps.thesis.models import Thesis
from apps.triggers.serializers import EventTriggerSerializer
from apps.triggers.services.thesis_guard import sync_thesis_guard


@pytest.mark.django_db
def test_trigger_serializer_exposes_source_thesis_id():
    p = TradingProfile.objects.create(name="P", default_includes=["quotes"])
    th = Thesis.objects.create(
        title="t",
        ticker="NVDA",
        direction="bullish",
        profile=p,
        target_price=200,
        guard_enabled=True,
    )
    g = sync_thesis_guard(th)
    assert EventTriggerSerializer(g).data["source_thesis_id"] == th.id
