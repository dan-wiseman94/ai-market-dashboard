"""Thesis <-> AI-prediction reconciliation (M13 F7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient

from apps.predictions.models import AIPrediction
from apps.predictions.services.reconcile import (
    ai_view_payload,
    current_ai_view,
    reconcile_directions,
)


def _pred(ticker="NVDA", direction="bullish", status="open", predicted_at=None):
    predicted_at = predicted_at or datetime(2026, 1, 5, tzinfo=UTC)
    return AIPrediction.objects.create(
        ticker=ticker,
        direction=direction,
        horizon_days=7,
        confidence=0.7,
        provider="claude",
        model="m",
        predicted_at=predicted_at,
        resolve_at=predicted_at + timedelta(days=7),
        status=status,
    )


@pytest.mark.parametrize(
    ("thesis_dir", "ai_dir", "expected"),
    [
        ("bullish", "bullish", "agree"),
        ("bearish", "bearish", "agree"),
        ("neutral", "neutral", "agree"),
        ("bullish", "bearish", "diverge"),
        ("bearish", "bullish", "diverge"),
        ("bullish", "neutral", "partial"),
        ("neutral", "bearish", "partial"),
    ],
)
def test_reconcile_directions(thesis_dir, ai_dir, expected):
    assert reconcile_directions(thesis_dir, ai_dir) == expected


@pytest.mark.django_db
class TestCurrentAIView:
    def test_returns_latest_open(self):
        _pred(predicted_at=datetime(2026, 1, 1, tzinfo=UTC))
        latest = _pred(direction="bearish", predicted_at=datetime(2026, 1, 10, tzinfo=UTC))
        assert current_ai_view("NVDA").id == latest.id

    def test_ignores_non_open(self):
        _pred(status="resolved")
        assert current_ai_view("NVDA") is None

    def test_none_when_no_view(self):
        assert current_ai_view("ZZZ") is None


@pytest.mark.django_db
class TestPayloadAndEndpoint:
    def test_payload_no_view(self):
        assert ai_view_payload("ZZZ") == {"ticker": "ZZZ", "has_view": False}

    def test_payload_with_agreement(self):
        _pred(direction="neutral")
        out = ai_view_payload("nvda", against="bullish")
        assert out["has_view"] is True
        assert out["direction"] == "neutral"
        assert out["horizon_days"] == 7
        assert out["agreement"] == "partial"

    def test_payload_agreement_null_without_against(self):
        _pred(direction="bullish")
        assert ai_view_payload("NVDA")["agreement"] is None

    def test_endpoint_agree(self):
        _pred(direction="bullish")
        resp = APIClient().get("/api/predictions/ai-view/?ticker=NVDA&against=bullish")
        assert resp.status_code == 200
        assert resp.json()["agreement"] == "agree"

    def test_endpoint_no_ticker(self):
        resp = APIClient().get("/api/predictions/ai-view/")
        assert resp.status_code == 200
        assert resp.json()["has_view"] is False
