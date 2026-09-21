from __future__ import annotations

import pytest
from django.apps import apps as django_apps

from apps.profiles.migrations import _enable_capabilities
from apps.profiles.models import TradingProfile
from apps.profiles.serializers import TradingProfileSerializer


@pytest.mark.django_db
def test_capability_flags_default_on():
    p = TradingProfile.objects.create(name="caps", style="s")
    assert p.enable_tools is True
    assert p.enable_thinking is True
    assert p.enable_memory is True
    assert p.effort == "high"


@pytest.mark.django_db
def test_capability_flags_stay_off_when_explicitly_set():
    p = TradingProfile.objects.create(
        name="quiet", style="s", enable_tools=False, enable_thinking=False, enable_memory=False
    )
    p.refresh_from_db()
    assert (p.enable_tools, p.enable_thinking, p.enable_memory) == (False, False, False)


@pytest.mark.django_db
def test_enable_capabilities_flips_existing_rows():
    p = TradingProfile.objects.create(name="old", style="s")
    TradingProfile.objects.filter(pk=p.pk).update(
        enable_tools=False, enable_thinking=False, enable_memory=False
    )
    _enable_capabilities.enable_capabilities(django_apps, None)
    p.refresh_from_db()
    assert (p.enable_tools, p.enable_thinking, p.enable_memory) == (True, True, True)


@pytest.mark.django_db
def test_serializer_exposes_and_writes_capability_fields():
    p = TradingProfile.objects.create(name="caps2", style="s")
    data = TradingProfileSerializer(p).data
    assert data["enable_tools"] is True
    assert data["enable_thinking"] is True
    assert data["enable_memory"] is True
    assert data["effort"] == "high"

    ser = TradingProfileSerializer(p, data={"enable_tools": False, "effort": "max"}, partial=True)
    assert ser.is_valid(), ser.errors
    obj = ser.save()
    assert obj.enable_tools is False
    assert obj.effort == "max"


@pytest.mark.django_db
def test_serializer_rejects_unknown_effort():
    p = TradingProfile.objects.create(name="caps3", style="s")
    ser = TradingProfileSerializer(p, data={"effort": "turbo"}, partial=True)
    assert not ser.is_valid()
    assert "effort" in ser.errors
