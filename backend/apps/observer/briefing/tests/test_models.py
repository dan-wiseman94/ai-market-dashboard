from datetime import date

import pytest
from django.db import IntegrityError

from apps.observer.models import BriefingRun


@pytest.mark.django_db
def test_scheduled_date_unique_claim():
    BriefingRun.objects.create(scheduled_date=date(2026, 5, 28), status="ready")
    with pytest.raises(IntegrityError):
        BriefingRun.objects.create(scheduled_date=date(2026, 5, 28), status="assembling")
