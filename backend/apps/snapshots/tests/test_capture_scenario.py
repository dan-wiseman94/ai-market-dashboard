"""Snapshot capture honors a propagated service scenario in the worker.

The mock scenario lives in a web-process ContextVar that does NOT cross into the
Celery worker; capture_task re-applies the ``scenario`` it is handed. Under
``news-503`` the finnhub-backed news section must fail while schwab-backed quotes
still succeed — a genuine partial failure.
"""

from unittest.mock import patch

import pytest
from django.test import override_settings

from apps.core.mocks import current_scenario
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot
from apps.snapshots.tasks import capture_task


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_task_propagates_news_503_and_marks_news_failed():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(
        profile=profile,
        objective="",
        includes=["quotes", "news"],
        source="manual",
        status="pending",
    )

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        capture_task(snapshot_id=snap.id, watchlist_tickers=["SPY"], scenario="news-503")

    snap.refresh_from_db()
    # Partial failure: quotes (schwab → "ok") succeeds, news (finnhub → 503) fails.
    assert snap.status == "ready"
    assert snap.sections.get(kind="quotes").status == "done"
    news = snap.sections.get(kind="news")
    assert news.status == "failed"
    assert "503" in news.error
    # The task restores the scenario ContextVar in its finally block.
    assert current_scenario() == "default"


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_task_default_scenario_keeps_news_done():
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(
        profile=profile,
        objective="",
        includes=["news"],
        source="manual",
        status="pending",
    )

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        capture_task(snapshot_id=snap.id, watchlist_tickers=["SPY"], scenario="default")

    snap.refresh_from_db()
    assert snap.sections.get(kind="news").status == "done"


@pytest.mark.django_db
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
def test_capture_task_propagates_schwab_401_and_fails_schwab_sections():
    from apps.market.cache import _redis

    # quotes/positions are Redis-cached (positions on a fixed key); a prior test may
    # have warmed them. Clear so capture actually calls the (gated) schwab client.
    r = _redis()
    for key in r.scan_iter("market:*"):
        r.delete(key)

    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(
        profile=profile,
        objective="",
        includes=["quotes", "positions", "news"],
        source="manual",
        status="pending",
    )

    with patch("apps.core.mocks.is_mock_mode", return_value=True):
        capture_task(snapshot_id=snap.id, watchlist_tickers=["SPY"], scenario="schwab-401")

    snap.refresh_from_db()
    # schwab is down (401) → quotes + positions fail; finnhub is fine → news succeeds.
    assert snap.status == "ready"
    assert snap.sections.get(kind="quotes").status == "failed"
    assert snap.sections.get(kind="positions").status == "failed"
    assert snap.sections.get(kind="news").status == "done"
