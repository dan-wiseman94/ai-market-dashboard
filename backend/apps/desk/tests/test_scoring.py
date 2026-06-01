import pytest

from apps.desk.models import DeskEntry
from apps.desk.services.scoring import in_cooldown, rank

pytestmark = pytest.mark.django_db


def test_rank_orders_by_severity():
    cands = [
        {"anomaly_type": "a", "ticker": "X", "severity": 1.0, "evidence": {}},
        {"anomaly_type": "b", "ticker": "Y", "severity": 9.0, "evidence": {}},
    ]
    ranked = rank(cands)
    assert ranked[0]["ticker"] == "Y"


def test_cooldown_blocks_recent_same_key():
    DeskEntry.objects.create(anomaly_type="price_move", ticker="X", severity=5.0)
    assert in_cooldown("price_move", "X") is True
    assert in_cooldown("price_move", "Z") is False
