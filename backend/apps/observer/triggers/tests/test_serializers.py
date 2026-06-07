import pytest

from apps.observer.models import EventTrigger, TriggerFiring
from apps.observer.triggers.serializers import (
    EventTriggerSerializer,
    TriggerFiringSerializer,
)
from apps.profiles.models import TradingProfile


@pytest.mark.django_db
def test_event_trigger_serializer_roundtrip():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(
        name="r",
        profile=p,
        condition={"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
    )
    data = EventTriggerSerializer(t).data
    assert data["name"] == "r"
    assert data["profile"] == p.id
    assert data["condition"] == {"metric": "price", "ticker": "SPY", "op": ">", "value": 550}
    assert data["enabled"] is True
    assert data["firings_count"] == 0


@pytest.mark.django_db
def test_event_trigger_serializer_validates_dsl_on_create():
    p = TradingProfile.objects.create(name="P", style="x")
    ser = EventTriggerSerializer(
        data={
            "name": "bad",
            "profile": p.id,
            "condition": {"metric": "nope", "op": ">", "value": 1},
            "cooldown_seconds": 300,
            "enabled": True,
        }
    )
    assert ser.is_valid() is False
    assert "condition" in ser.errors


@pytest.mark.django_db
def test_event_trigger_serializer_accepts_valid_dsl():
    p = TradingProfile.objects.create(name="P", style="x")
    ser = EventTriggerSerializer(
        data={
            "name": "ok",
            "profile": p.id,
            "condition": {
                "all": [
                    {"metric": "price", "ticker": "SPY", "op": ">", "value": 550},
                ]
            },
            "cooldown_seconds": 600,
            "enabled": True,
        }
    )
    assert ser.is_valid(), ser.errors
    obj = ser.save()
    assert obj.name == "ok"


@pytest.mark.django_db
def test_firings_count_annotation_reflects_rows():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="r", profile=p, condition={"all": []})
    TriggerFiring.objects.create(trigger=t, matched_values={})
    TriggerFiring.objects.create(trigger=t, matched_values={})

    from django.db.models import Count

    qs = EventTrigger.objects.annotate(firings_count=Count("firings"))
    data = EventTriggerSerializer(qs.get(id=t.id)).data
    assert data["firings_count"] == 2


@pytest.mark.django_db
def test_trigger_firing_serializer_shape():
    p = TradingProfile.objects.create(name="P", style="x")
    t = EventTrigger.objects.create(name="SPY>550", profile=p, condition={"all": []})
    f = TriggerFiring.objects.create(
        trigger=t,
        matched_values={"price:SPY": 551.2},
        cost_capped=False,
    )
    data = TriggerFiringSerializer(f).data
    assert data["trigger_id"] == t.id
    assert data["trigger_name"] == "SPY>550"
    assert data["matched_values"] == {"price:SPY": 551.2}
    assert data["snapshot_id"] is None
    assert data["thread_id"] is None
    assert data["cost_capped"] is False
    assert "fired_at" in data
