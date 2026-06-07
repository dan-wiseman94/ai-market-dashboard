"""Live AI prediction calibration (M13 F3) — the AI's own resolved-prediction track record."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from rest_framework.test import APIClient

from apps.analytics.services.ai_calibration import ai_calibration, ai_calibration_drilldown
from apps.observer.models import AIPrediction

WIN_START = datetime(2026, 1, 1, tzinfo=UTC)
WIN_END = datetime(2026, 2, 1, tzinfo=UTC)
_RESOLVED_AT = datetime(2026, 1, 20, 12, 0, tzinfo=UTC)


def _resolved(confidence, verdict, *, direction="bullish", provider="claude", model="m", horizon=7):
    return AIPrediction.objects.create(
        ticker="NVDA",
        direction=direction,
        horizon_days=horizon,
        confidence=confidence,
        provider=provider,
        model=model,
        predicted_at=_RESOLVED_AT - timedelta(days=7),
        resolve_at=_RESOLVED_AT,
        status="resolved",
        verdict=verdict,
        forward_return_pct=5.0 if verdict == "correct" else -5.0,
        resolved_at=_RESOLVED_AT,
    )


@pytest.mark.django_db
class TestAICalibration:
    def test_overall_hit_rate_and_brier(self):
        _resolved(0.8, "correct")
        _resolved(0.8, "incorrect")
        _resolved(0.7, "correct")
        out = ai_calibration(start=WIN_START, end=WIN_END)
        assert out["overall"]["scored"] == 3
        assert out["overall"]["hit_rate"] == pytest.approx(2 / 3, abs=1e-3)
        # Brier = mean((conf-outcome)^2) = (.04 + .64 + .09) / 3
        assert out["brier"] == pytest.approx(0.77 / 3, abs=1e-3)

    def test_inconclusive_excluded(self):
        _resolved(0.8, "correct")
        AIPrediction.objects.create(
            ticker="X",
            direction="bullish",
            horizon_days=7,
            confidence=0.9,
            provider="claude",
            model="m",
            predicted_at=WIN_START,
            resolve_at=WIN_START,
            status="resolved",
            verdict="inconclusive",
            forward_return_pct=None,
            resolved_at=_RESOLVED_AT,
        )
        assert ai_calibration(start=WIN_START, end=WIN_END)["overall"]["scored"] == 1

    def test_per_provider_model_hit_rate(self):
        _resolved(0.8, "correct", provider="claude", model="opus")
        _resolved(0.8, "incorrect", provider="openai", model="gpt5")
        models = {
            (r["provider"], r["model"]): r
            for r in ai_calibration(start=WIN_START, end=WIN_END)["by_provider_model"]
        }
        assert models[("claude", "opus")]["hit_rate"] == 1.0
        assert models[("openai", "gpt5")]["hit_rate"] == 0.0

    def test_reliability_band_reconciles_with_drilldown(self):
        _resolved(0.85, "correct")
        _resolved(0.85, "incorrect")
        out = ai_calibration(start=WIN_START, end=WIN_END)
        band = next(b for b in out["reliability"] if b["band"] == "0.8-0.9")
        assert band["n"] == 2
        assert band["observed_hit_rate"] == pytest.approx(0.5)
        dd = ai_calibration_drilldown(start=WIN_START, end=WIN_END, band="0.8-0.9")
        assert dd["count"] == band["n"]  # same population

    def test_horizon_filter(self):
        _resolved(0.8, "correct", horizon=7)
        _resolved(0.8, "correct", horizon=30)
        assert ai_calibration(start=WIN_START, end=WIN_END, horizon=30)["overall"]["scored"] == 1


@pytest.mark.django_db
def test_ai_calibration_endpoints_200():
    _resolved(0.85, "correct")  # resolved_at is in Jan 2026
    rng = "start=2026-01-01&end=2026-02-01"
    resp = APIClient().get(f"/api/analytics/ai-calibration/?{rng}")
    assert resp.status_code == 200
    assert resp.json()["overall"]["scored"] == 1
    dd = APIClient().get(f"/api/analytics/ai-calibration/drilldown/?{rng}&band=0.8-0.9")
    assert dd.status_code == 200
    assert dd.json()["count"] == 1
