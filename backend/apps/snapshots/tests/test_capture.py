from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.profiles.models import TradingProfile
from apps.snapshots.services import capture


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_creates_snapshot_with_sections():
    p = TradingProfile.objects.create(name="P", style="x")

    with (
        patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 550}}),
        patch(
            "apps.snapshots.services.fetch_positions", return_value=[{"ticker": "SPY", "qty": 1}]
        ),
    ):
        snap = capture(
            profile=p,
            objective="short SPY?",
            includes=["quotes", "positions"],
            notes="",
            source="manual",
            watchlist_tickers=["SPY"],
        )

    snap.refresh_from_db()
    assert snap.status == "ready"
    kinds = list(snap.sections.values_list("kind", "status"))
    assert ("quotes", "done") in kinds
    assert ("positions", "done") in kinds


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_records_partial_failure():
    p = TradingProfile.objects.create(name="P", style="x")

    with (
        patch("apps.snapshots.services.fetch_quotes", return_value={"SPY": {"last": 550}}),
        patch("apps.snapshots.services.fetch_positions", side_effect=RuntimeError("schwab down")),
    ):
        snap = capture(
            profile=p,
            objective="",
            includes=["quotes", "positions"],
            notes="",
            source="manual",
            watchlist_tickers=["SPY"],
        )

    snap.refresh_from_db()
    assert snap.status == "ready"
    quotes_sec = snap.sections.get(kind="quotes")
    positions_sec = snap.sections.get(kind="positions")
    assert quotes_sec.status == "done"
    assert positions_sec.status == "failed"
    assert "schwab down" in positions_sec.error


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_scrubs_credentials_from_section_error():
    p = TradingProfile.objects.create(name="P", style="x")
    leaky = RuntimeError(
        "403 Client Error for url: https://finnhub.io/api/v1/news?symbol=SPY&token=SECRETKEY99"
    )

    with patch("apps.snapshots.services.fetch_quotes", side_effect=leaky):
        snap = capture(
            profile=p,
            objective="",
            includes=["quotes"],
            notes="",
            source="manual",
            watchlist_tickers=["SPY"],
        )

    err = snap.sections.get(kind="quotes").error
    assert "SECRETKEY99" not in err
    assert "token=***" in err
    assert "403 Client Error" in err  # diagnostics survive the scrub


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_fails_when_all_sections_fail():
    p = TradingProfile.objects.create(name="P", style="x")

    with patch("apps.snapshots.services.fetch_quotes", side_effect=RuntimeError("down")):
        snap = capture(
            profile=p,
            objective="",
            includes=["quotes"],
            notes="",
            source="manual",
            watchlist_tickers=["SPY"],
        )

    snap.refresh_from_db()
    assert snap.status == "failed"
