import pytest

from apps.strategy.models import WarRoomRun
from apps.threads.models import Thread

pytestmark = pytest.mark.django_db


def test_create_and_str():
    th = Thread.objects.create(kind="warroom", title="Debate: NVDA")
    run = WarRoomRun.objects.create(
        thread=th,
        subject_kind="free",
        subject_label="NVDA into earnings",
        params={"structure": "rebuttal"},
        verdict={"verdict": "balanced"},
        confidence=0.6,
    )
    assert run.confidence == 0.6
    assert "NVDA" in str(run)
