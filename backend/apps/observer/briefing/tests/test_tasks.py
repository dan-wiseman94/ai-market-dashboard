from datetime import datetime, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from apps.observer.briefing.tasks import run_scheduled
from apps.observer.models import BriefingConfig

UTC = ZoneInfo("UTC")


@pytest.mark.django_db
def test_skips_when_disabled():
    cfg = BriefingConfig.load()
    cfg.enabled = False
    cfg.save()
    assert run_scheduled() == {"skipped": "disabled"}


@pytest.mark.django_db
def test_skips_before_send_at():
    cfg = BriefingConfig.load()
    cfg.send_at_local = time(8, 30)
    cfg.save()
    with patch(
        "apps.observer.briefing.tasks._now_local", return_value=datetime(2026, 5, 28, 7, 0, tzinfo=UTC)
    ):
        assert run_scheduled() == {"skipped": "before_send_at"}


@pytest.mark.django_db
def test_fires_when_due():
    cfg = BriefingConfig.load()
    cfg.send_at_local = time(8, 30)
    cfg.save()
    with (
        patch(
            "apps.observer.briefing.tasks._now_local", return_value=datetime(2026, 5, 28, 9, 0, tzinfo=UTC)
        ),
        patch("apps.observer.briefing.tasks.run_briefing", return_value=type("R", (), {"id": 7})()) as rb,
    ):
        assert run_scheduled() == {"ran": 7}
        rb.assert_called_once_with(scheduled=True)
