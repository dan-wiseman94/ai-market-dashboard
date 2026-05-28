from datetime import date

import pytest
from django.db import IntegrityError

from apps.briefing.models import BriefingConfig, BriefingRun


@pytest.mark.django_db
def test_briefing_config_is_singleton():
    a = BriefingConfig.load()
    b = BriefingConfig.load()
    assert a.pk == b.pk == 1
    assert a.enabled is True


@pytest.mark.django_db
def test_scheduled_date_unique_claim():
    BriefingRun.objects.create(scheduled_date=date(2026, 5, 28), status="ready")
    with pytest.raises(IntegrityError):
        BriefingRun.objects.create(scheduled_date=date(2026, 5, 28), status="assembling")


@pytest.mark.django_db
def test_manual_runs_have_null_scheduled_date_and_are_unlimited():
    BriefingRun.objects.create(scheduled_date=None, status="ready")
    BriefingRun.objects.create(scheduled_date=None, status="ready")
    assert BriefingRun.objects.filter(scheduled_date__isnull=True).count() == 2
