import inspect

import pytest

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture_for_existing
from apps.snapshots.tasks import capture_task


def test_capture_for_existing_has_no_overnight_param():
    assert "overnight" not in inspect.signature(capture_for_existing).parameters


def test_capture_task_has_no_overnight_param():
    assert "overnight" not in inspect.signature(capture_task).parameters


@pytest.mark.django_db
def test_quotes_fetcher_uses_default_gap_context():
    from unittest.mock import patch

    profile = TradingProfile.objects.create(name="t", default_provider="openai")
    from apps.snapshots.models import Snapshot

    snap = Snapshot.objects.create(profile=profile, includes=["quotes"], status="pending")
    with patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 1}}) as m:
        capture_for_existing(snap, watchlist_tickers=["SPY"])
    assert m.call_args.kwargs.get("gap_context", False) is False
