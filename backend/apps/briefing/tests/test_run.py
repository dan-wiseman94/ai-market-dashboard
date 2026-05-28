from datetime import date
from unittest.mock import patch

import pytest

from apps.briefing.models import BriefingConfig, BriefingRun
from apps.briefing.services import run as R
from apps.profiles.models import TradingProfile


@pytest.fixture
def cfg(db):
    c = BriefingConfig.load()
    c.profile = TradingProfile.objects.create(name="B", style="brief")
    c.save()
    return c


@pytest.mark.django_db
def test_render_briefing_markdown_mentions_sections():
    md = R.render_briefing_markdown(
        {
            "theses": [
                {
                    "ticker": "NVDA",
                    "direction": "bullish",
                    "current": 100,
                    "pct_to_target": 10,
                    "pct_to_invalidation": -10,
                    "conviction": 4,
                }
            ],
            "events": {"earnings": [{"ticker": "NVDA", "days_until": 2}], "macro": []},
            "triggers": [],
            "news": [],
            "market": {"vix_last": 18},
            "since": "x",
        }
    )
    assert "NVDA" in md and "Upcoming" in md


@pytest.mark.django_db
def test_run_briefing_manual_creates_run_and_dispatches_ai(cfg):
    with (
        patch(
            "apps.briefing.services.run.assemble", return_value=({"theses": [], "since": "x"}, None)
        ),
        patch("apps.briefing.services.run.run_ai_on_message.delay") as delay,
        patch("apps.briefing.services.run.notify") as notify,
    ):
        run = R.run_briefing(scheduled=False)
    assert run.status == "ready"
    assert run.scheduled_date is None
    assert run.synthesis_message is not None
    delay.assert_called_once()
    notify.assert_called_once()
    assert notify.call_args.kwargs["kind"] == "briefing"


@pytest.mark.django_db
def test_run_briefing_scheduled_is_idempotent_per_day(cfg):
    with (
        patch("apps.briefing.services.run.assemble", return_value=({"since": "x"}, None)),
        patch("apps.briefing.services.run.run_ai_on_message.delay"),
        patch("apps.briefing.services.run.notify"),
        patch("apps.briefing.services.run._local_today", return_value=date(2026, 5, 28)),
    ):
        first = R.run_briefing(scheduled=True)
        second = R.run_briefing(scheduled=True)
    assert first is not None and first.scheduled_date == date(2026, 5, 28)
    assert second is None
    assert BriefingRun.objects.filter(scheduled_date=date(2026, 5, 28)).count() == 1
