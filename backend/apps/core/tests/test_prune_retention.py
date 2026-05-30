"""Tests for the core.prune_retention beat task.

Safety contract verified here:
  1. prunes-old-keeps-recent   — old rows deleted, recent rows survive, counts exact
  2. unresolved-errors-survive — ErrorEvent(resolved=False) kept regardless of age
  3. protected-models-untouched — Snapshot / Message / Thesis are NEVER deleted
  4. never-raises              — a model's filter() exploding → label==-1, rest run
  5. idempotent                — second run deletes 0 on all labels
  6. beat-registration         — "prune-retention" entry exists in beat_schedule
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.core.models import ErrorEvent
from apps.core.tasks import prune_retention
from apps.market.models import OHLCBar, OptionChainSnapshot
from apps.observer.models import Notification

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_NOW = timezone.now


def _ohlc(days_ago: int, ticker: str = "SPY") -> OHLCBar:
    bar = OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1d",
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1_000_000,
        ts=_NOW(),  # placeholder; update after
    )
    OHLCBar.objects.filter(pk=bar.pk).update(ts=_NOW() - timedelta(days=days_ago))
    return bar


def _chain(days_ago: int, ticker: str = "SPY") -> OptionChainSnapshot:
    snap = OptionChainSnapshot.objects.create(ticker=ticker, payload={})
    OptionChainSnapshot.objects.filter(pk=snap.pk).update(
        fetched_at=_NOW() - timedelta(days=days_ago)
    )
    return snap


def _notification(days_ago: int) -> Notification:
    n = Notification.objects.create(kind="trigger", title="test")
    Notification.objects.filter(pk=n.pk).update(created_at=_NOW() - timedelta(days=days_ago))
    return n


def _error(days_ago: int, resolved: bool) -> ErrorEvent:
    ev = ErrorEvent.objects.create(source="test", message="boom", resolved=resolved)
    ErrorEvent.objects.filter(pk=ev.pk).update(created_at=_NOW() - timedelta(days=days_ago))
    return ev


# ---------------------------------------------------------------------------
# 1. prunes-old-keeps-recent
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_prunes_old_ohlc_keeps_recent(settings):
    settings.AI_RETENTION_OHLC_DAYS = 400
    settings.AI_RETENTION_CHAIN_DAYS = 120
    settings.AI_RETENTION_NOTIFICATION_DAYS = 90
    settings.AI_RETENTION_ERROR_DAYS = 90

    old1 = _ohlc(days_ago=401)
    old2 = _ohlc(days_ago=600)
    recent = _ohlc(days_ago=5)

    result = prune_retention()

    # old rows gone
    assert not OHLCBar.objects.filter(pk=old1.pk).exists()
    assert not OHLCBar.objects.filter(pk=old2.pk).exists()
    # recent row survives
    assert OHLCBar.objects.filter(pk=recent.pk).exists()
    # count matches
    assert result["ohlc"] == 2


@pytest.mark.django_db
def test_prunes_old_chain_keeps_recent(settings):
    settings.AI_RETENTION_OHLC_DAYS = 400
    settings.AI_RETENTION_CHAIN_DAYS = 120
    settings.AI_RETENTION_NOTIFICATION_DAYS = 90
    settings.AI_RETENTION_ERROR_DAYS = 90

    old = _chain(days_ago=121)
    recent = _chain(days_ago=10)

    result = prune_retention()

    assert not OptionChainSnapshot.objects.filter(pk=old.pk).exists()
    assert OptionChainSnapshot.objects.filter(pk=recent.pk).exists()
    assert result["chain"] == 1


@pytest.mark.django_db
def test_prunes_old_notifications_keeps_recent(settings):
    settings.AI_RETENTION_OHLC_DAYS = 400
    settings.AI_RETENTION_CHAIN_DAYS = 120
    settings.AI_RETENTION_NOTIFICATION_DAYS = 90
    settings.AI_RETENTION_ERROR_DAYS = 90

    old = _notification(days_ago=91)
    recent = _notification(days_ago=5)

    result = prune_retention()

    assert not Notification.objects.filter(pk=old.pk).exists()
    assert Notification.objects.filter(pk=recent.pk).exists()
    assert result["notifications"] == 1


@pytest.mark.django_db
def test_prunes_only_resolved_old_errors_keeps_recent(settings):
    """Resolved+old → deleted. Unresolved+old → KEPT. Recent resolved → KEPT."""
    settings.AI_RETENTION_OHLC_DAYS = 400
    settings.AI_RETENTION_CHAIN_DAYS = 120
    settings.AI_RETENTION_NOTIFICATION_DAYS = 90
    settings.AI_RETENTION_ERROR_DAYS = 90

    resolved_old = _error(days_ago=91, resolved=True)
    unresolved_old = _error(days_ago=91, resolved=False)
    resolved_recent = _error(days_ago=5, resolved=True)

    result = prune_retention()

    # resolved+old: gone
    assert not ErrorEvent.objects.filter(pk=resolved_old.pk).exists()
    # unresolved+old: KEPT regardless of age (safety — don't lose unresolved errors)
    assert ErrorEvent.objects.filter(pk=unresolved_old.pk).exists()
    # resolved+recent: KEPT
    assert ErrorEvent.objects.filter(pk=resolved_recent.pk).exists()
    assert result["errors"] == 1


# ---------------------------------------------------------------------------
# 2. unresolved-errors-survive (explicit, standalone)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_unresolved_errors_survive_regardless_of_age(settings):
    """The critical safety case: even a very old unresolved error is never pruned."""
    settings.AI_RETENTION_OHLC_DAYS = 400
    settings.AI_RETENTION_CHAIN_DAYS = 120
    settings.AI_RETENTION_NOTIFICATION_DAYS = 90
    settings.AI_RETENTION_ERROR_DAYS = 90

    # 10 years old, unresolved
    ancient_unresolved = _error(days_ago=3650, resolved=False)

    result = prune_retention()

    assert ErrorEvent.objects.filter(pk=ancient_unresolved.pk).exists(), (
        "Unresolved ErrorEvent must NEVER be pruned regardless of age"
    )
    assert result["errors"] == 0


# ---------------------------------------------------------------------------
# 3. protected-models-untouched
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_protected_models_never_pruned(settings):
    """Snapshot, Message (via Thread), and Thesis are never deleted by prune_retention.

    We create both recent and ancient rows for each protected model, run the
    task, and assert every row still exists. Even setting windows to 0 days
    must leave these tables untouched because the task never references them.
    """
    from apps.profiles.models import TradingProfile
    from apps.snapshots.models import Snapshot
    from apps.thesis.models import Thesis
    from apps.threads.models import Message, Thread

    settings.AI_RETENTION_OHLC_DAYS = 0  # if it were to touch these, everything would go
    settings.AI_RETENTION_CHAIN_DAYS = 0
    settings.AI_RETENTION_NOTIFICATION_DAYS = 0
    settings.AI_RETENTION_ERROR_DAYS = 0

    profile = TradingProfile.objects.create(name="Test", style="scalper")

    # Snapshot — recent
    snap_recent = Snapshot.objects.create(profile=profile, status="ready")
    # Snapshot — very old (Snapshot uses captured_at, not created_at)
    snap_old = Snapshot.objects.create(profile=profile, status="ready")
    Snapshot.objects.filter(pk=snap_old.pk).update(captured_at=_NOW() - timedelta(days=3650))

    # Thread + Message
    thread = Thread.objects.create(kind="consult", profile=profile)
    msg_recent = Message.objects.create(thread=thread, role="user", content={"text": "hi"})
    msg_old = Message.objects.create(thread=thread, role="user", content={"text": "old"})
    Message.objects.filter(pk=msg_old.pk).update(created_at=_NOW() - timedelta(days=3650))

    # Thesis — requires only title, ticker, direction
    thesis_recent = Thesis.objects.create(title="T1", ticker="AAPL", direction="bullish")
    thesis_old = Thesis.objects.create(title="T2", ticker="AAPL", direction="bearish")
    Thesis.objects.filter(pk=thesis_old.pk).update(created_at=_NOW() - timedelta(days=3650))

    # Run with windows of 0 — if the task touched these models, everything would vanish
    prune_retention()

    # Every single protected row must still exist
    assert Snapshot.objects.filter(pk=snap_recent.pk).exists(), "recent Snapshot deleted"
    assert Snapshot.objects.filter(pk=snap_old.pk).exists(), "old Snapshot deleted"
    assert Message.objects.filter(pk=msg_recent.pk).exists(), "recent Message deleted"
    assert Message.objects.filter(pk=msg_old.pk).exists(), "old Message deleted"
    assert Thesis.objects.filter(pk=thesis_recent.pk).exists(), "recent Thesis deleted"
    assert Thesis.objects.filter(pk=thesis_old.pk).exists(), "old Thesis deleted"


# ---------------------------------------------------------------------------
# 4. never-raises
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_never_raises_when_one_model_explodes(settings, monkeypatch):
    """If one model's filter() raises, the task must NOT propagate — it logs
    the failure (label == -1) and continues pruning all other models."""
    settings.AI_RETENTION_OHLC_DAYS = 400
    settings.AI_RETENTION_CHAIN_DAYS = 120
    settings.AI_RETENTION_NOTIFICATION_DAYS = 90
    settings.AI_RETENTION_ERROR_DAYS = 90

    # Create an old notification that WILL be pruned (proves others still run)
    old_notification = _notification(days_ago=91)

    # Blow up OHLCBar.objects.filter
    original_filter = OHLCBar.objects.filter

    def _exploding_filter(*args, **kwargs):
        if "ts__lt" in kwargs:
            raise RuntimeError("simulated DB failure on ohlc")
        return original_filter(*args, **kwargs)

    monkeypatch.setattr(OHLCBar.objects, "filter", _exploding_filter)

    # Must NOT raise
    result = prune_retention()

    # Failed label == -1
    assert result["ohlc"] == -1, "exploding model must produce label == -1"

    # Other models still ran — notification was pruned
    assert not Notification.objects.filter(pk=old_notification.pk).exists(), (
        "other models must still run when one fails"
    )
    assert result["notifications"] >= 1


# ---------------------------------------------------------------------------
# 5. idempotent
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_idempotent_second_run_deletes_zero(settings):
    """Running prune_retention twice: second run deletes 0 on all labels."""
    settings.AI_RETENTION_OHLC_DAYS = 400
    settings.AI_RETENTION_CHAIN_DAYS = 120
    settings.AI_RETENTION_NOTIFICATION_DAYS = 90
    settings.AI_RETENTION_ERROR_DAYS = 90

    _ohlc(days_ago=401)
    _chain(days_ago=121)
    _notification(days_ago=91)
    _error(days_ago=91, resolved=True)

    first = prune_retention()
    assert first["ohlc"] == 1
    assert first["chain"] == 1
    assert first["notifications"] == 1
    assert first["errors"] == 1

    second = prune_retention()
    assert second["ohlc"] == 0
    assert second["chain"] == 0
    assert second["notifications"] == 0
    assert second["errors"] == 0


# ---------------------------------------------------------------------------
# 6. beat-registration
# ---------------------------------------------------------------------------


def test_beat_registration():
    """'prune-retention' must exist in the beat schedule with the correct task name."""
    from config.celery import app

    schedule = app.conf.beat_schedule
    assert "prune-retention" in schedule, (
        "'prune-retention' not found in beat_schedule — beat task won't fire"
    )
    assert schedule["prune-retention"]["task"] == "core.prune_retention"
