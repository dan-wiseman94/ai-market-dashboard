"""Auto-resolution of AI predictions (M13 F2) — deterministic, C3-correct, idempotent."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from django.utils import timezone

from apps.market.models import CorporateAction, OHLCBar
from apps.observer.models import AIPrediction
from apps.observer.predictions.tasks import resolve_due, resolve_prediction

START = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
END = datetime(2026, 1, 12, 15, 0, tzinfo=UTC)


def _mk_bar(ticker, ts, close):
    OHLCBar.objects.create(
        ticker=ticker,
        timeframe="1h",
        ts=ts,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1,
    )


def _pred(*, ticker="NVDA", direction="bullish", predicted_at=START, resolve_at=END):
    return AIPrediction.objects.create(
        ticker=ticker,
        direction=direction,
        horizon_days=7,
        confidence=0.7,
        provider="claude",
        model="m",
        predicted_at=predicted_at,
        resolve_at=resolve_at,
        status="open",
    )


@pytest.mark.django_db
class TestResolve:
    def test_resolves_with_forward_return_and_verdict(self):
        _mk_bar("NVDA", START, 100.0)
        _mk_bar("NVDA", END, 110.0)
        pred = _pred()
        assert resolve_prediction(pred.id) is True
        pred.refresh_from_db()
        assert pred.status == "resolved"
        assert pred.forward_return_pct == pytest.approx(10.0)
        assert pred.verdict == "correct"  # bullish + 10%
        assert pred.resolved_at is not None

    def test_idempotent_second_resolve_is_noop(self):
        _mk_bar("NVDA", START, 100.0)
        _mk_bar("NVDA", END, 110.0)
        pred = _pred()
        assert resolve_prediction(pred.id) is True
        assert resolve_prediction(pred.id) is False  # already resolved — no double-score

    def test_no_price_history_is_inconclusive(self):
        pred = _pred()
        assert resolve_prediction(pred.id) is True
        pred.refresh_from_db()
        assert pred.forward_return_pct is None
        assert pred.verdict == "inconclusive"

    def test_split_in_window_resolves_flat_not_crashed(self):
        # 3:1 split divides price to 1/3; a neutral call should read FLAT (correct),
        # not a -66% crash — proving the ledger inherits C3 corporate-action math.
        _mk_bar("NVDA", START, 300.0)
        _mk_bar("NVDA", END, 100.0)
        CorporateAction.objects.create(
            source="test",
            external_id="SPLIT:NVDA:x",
            kind="split",
            ticker="NVDA",
            ex_date=date(2026, 1, 8),
            ratio=3.0,
        )
        pred = _pred(direction="neutral")
        resolve_prediction(pred.id)
        pred.refresh_from_db()
        assert pred.forward_return_pct == pytest.approx(0.0)
        assert pred.verdict == "correct"

    def test_resolve_due_only_picks_elapsed(self):
        now = timezone.now()
        past = _pred(
            ticker="AAA", predicted_at=now - timedelta(days=10), resolve_at=now - timedelta(days=1)
        )
        future = _pred(ticker="BBB", predicted_at=now, resolve_at=now + timedelta(days=7))
        out = resolve_due()
        past.refresh_from_db()
        future.refresh_from_db()
        assert past.status == "resolved"
        assert future.status == "open"
        assert out["resolved"] == 1
