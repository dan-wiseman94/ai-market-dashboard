"""Consistency sentinel: a new directional call vs the AI's stated view."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.observer.models import AIPrediction, Notification
from apps.observer.predictions.services.consistency import find_contradictions, open_contradictions
from apps.strategy.models import CoverageNote


def _note(ticker, stance):
    return CoverageNote.objects.create(ticker=ticker, stance=stance)


def _pred(ticker, direction, status="open"):
    now = timezone.now()
    return AIPrediction.objects.create(
        ticker=ticker,
        direction=direction,
        horizon_days=7,
        confidence=0.6,
        provider="claude",
        model="m",
        predicted_at=now,
        resolve_at=now,
        status=status,
    )


@pytest.mark.django_db
def test_bullish_call_contradicts_bear_house_view():
    _note("NVDA", "bear")
    c = find_contradictions("NVDA", "bullish")
    assert any(x["source"] == "coverage" and x["stance"] == "bear" for x in c)


@pytest.mark.django_db
def test_same_direction_is_consistent():
    _note("NVDA", "bull")
    assert find_contradictions("NVDA", "bullish") == []


@pytest.mark.django_db
def test_neutral_never_contradicts():
    _note("NVDA", "bear")
    assert find_contradictions("NVDA", "neutral") == []


@pytest.mark.django_db
def test_open_opposite_prediction_contradicts():
    p = _pred("NVDA", "bearish")
    c = find_contradictions("NVDA", "bullish")
    assert any(x["source"] == "prediction" and x["prediction_id"] == p.id for x in c)


@pytest.mark.django_db
def test_open_contradictions_lists_opposing_calls():
    _note("NVDA", "bull")
    _pred("NVDA", "bearish")  # open bearish vs bull house view
    _note("AAPL", "bull")
    _pred("AAPL", "bullish")  # consistent — excluded
    rows = open_contradictions()
    assert [r["ticker"] for r in rows] == ["NVDA"]


@pytest.mark.django_db
def test_flag_contradictions_notifies_then_silent_when_consistent():
    from apps.observer.predictions.services import extract

    _note("NVDA", "bear")
    extract._flag_contradictions("NVDA", "bullish")
    assert Notification.objects.filter(kind="contra").count() == 1

    _note("AAPL", "bull")
    extract._flag_contradictions("AAPL", "bullish")  # consistent → no new alert
    assert Notification.objects.filter(kind="contra").count() == 1
