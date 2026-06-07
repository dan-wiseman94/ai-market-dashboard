"""Thesis <-> AI-prediction reconciliation (M13 F7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient

from apps.observer.models import AIPrediction
from apps.observer.predictions.services.reconcile import (
    ai_view_payload,
    current_ai_view,
    open_divergences,
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


@pytest.mark.django_db
class TestOpenDivergences:
    def _thesis(self, *, ticker="NVDA", direction="bullish", status="open"):
        from apps.thesis.models import Thesis

        return Thesis.objects.create(
            title=f"{direction} {ticker}",
            ticker=ticker,
            direction=direction,
            conviction=4,
            status=status,
        )

    def test_lists_diverging_theses(self):
        self._thesis(direction="bullish")
        _pred(ticker="NVDA", direction="bearish")  # AI disagrees
        [row] = open_divergences()
        assert row["ticker"] == "NVDA"
        assert row["agreement"] == "diverge"
        assert row["thesis_direction"] == "bullish"
        assert row["ai_direction"] == "bearish"

    def test_excludes_agreement(self):
        self._thesis(direction="bullish")
        _pred(ticker="NVDA", direction="bullish")
        assert open_divergences() == []

    def test_skips_theses_without_ai_view(self):
        self._thesis(ticker="ZZZ", direction="bullish")
        assert open_divergences() == []

    def test_partial_toggle(self):
        self._thesis(direction="bullish")
        _pred(ticker="NVDA", direction="neutral")  # partial divergence
        assert len(open_divergences(include_partial=True)) == 1
        assert open_divergences(include_partial=False) == []

    def test_excludes_closed_theses(self):
        self._thesis(direction="bullish", status="closed_win")
        _pred(ticker="NVDA", direction="bearish")
        assert open_divergences() == []

    def test_endpoint(self):
        self._thesis(direction="bullish")
        _pred(ticker="NVDA", direction="bearish")
        resp = APIClient().get("/api/predictions/divergences/")
        assert resp.status_code == 200
        assert resp.json()["count"] == 1

    def test_no_n_plus_1_over_theses(self, django_assert_max_num_queries):
        # N diverging theses on distinct tickers must not cost one AI-view query
        # each — the AI views are bulk-fetched (1 Thesis + 1 AIPrediction query).
        for tk in ("AAA", "BBB", "CCC"):
            self._thesis(ticker=tk, direction="bullish")
            _pred(ticker=tk, direction="bearish")
        with django_assert_max_num_queries(3):  # a per-thesis loop would be 4+
            rows = open_divergences()
        assert len(rows) == 3
