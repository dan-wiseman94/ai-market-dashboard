from __future__ import annotations

import pytest

from apps.profiles.models import TradingProfile
from apps.profiles.serializers import TradingProfileSerializer


@pytest.mark.django_db
def test_enable_coach_defaults_true():
    p = TradingProfile.objects.create(name="x", style="s")
    assert p.enable_coach is True


@pytest.mark.django_db
def test_serializer_exposes_and_writes_enable_coach():
    p = TradingProfile.objects.create(name="x", style="s")
    assert TradingProfileSerializer(p).data["enable_coach"] is True

    ser = TradingProfileSerializer(p, data={"enable_coach": False}, partial=True)
    assert ser.is_valid(), ser.errors
    obj = ser.save()
    assert obj.enable_coach is False
