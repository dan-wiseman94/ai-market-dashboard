import pytest
from rest_framework.test import APIClient

from apps.strategy.models import DeskEntry

pytestmark = pytest.mark.django_db


def test_dashboard_desk_populated():
    DeskEntry.objects.create(
        anomaly_type="price_move", ticker="NVDA", severity=9.0, finding="NVDA gapped", status="new"
    )
    body = APIClient().get("/api/dashboard/").json()
    assert body["desk"]["unread"] == 1
    assert body["desk"]["latest"] == "NVDA gapped"
