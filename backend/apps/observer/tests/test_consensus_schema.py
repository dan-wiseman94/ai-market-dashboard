"""ConsensusReport schema + consensus flag default."""

from __future__ import annotations

import pytest

from apps.observer.models import ObserverSchedule
from apps.observer.schemas import ConsensusReport, ProviderTake
from apps.profiles.models import TradingProfile

pytestmark = pytest.mark.django_db


def test_consensus_report_round_trips():
    report = ConsensusReport(
        n_providers=3,
        bias_agreement=0.6667,
        modal_bias="bullish",
        divergent=True,
        per_ticker={
            "AAPL": {
                "agreement": 0.6667,
                "modal": "bullish",
                "takes": {"claude-a": "bullish", "claude-b": "bearish"},
            }
        },
        takes=[
            ProviderTake(provider="claude", model="m1", bias="bullish"),
            ProviderTake(provider="claude", model="m2", bias="bearish"),
        ],
        note="",
    )
    dumped = report.model_dump()
    again = ConsensusReport.model_validate(dumped)
    assert again.n_providers == 3
    assert again.modal_bias == "bullish"
    assert again.bias_agreement == 0.6667
    assert again.divergent is True
    assert again.per_ticker["AAPL"]["modal"] == "bullish"
    assert again.takes[1].bias == "bearish"


def test_consensus_report_degraded_defaults():
    """Honest single-provider shape: None agreement, no fake consensus."""
    report = ConsensusReport(
        n_providers=1,
        modal_bias="neutral",
        note="single provider — no consensus available",
    )
    assert report.bias_agreement is None
    assert report.divergent is False
    assert report.per_ticker == {}
    assert report.takes == []
    assert "single provider" in report.note


def test_consensus_flag_defaults_false():
    profile = TradingProfile.objects.create(
        name="P",
        default_provider="claude",
        default_model="claude-opus-4-8",
        default_includes=["quotes"],
    )
    sched = ObserverSchedule.objects.create(
        name="S",
        profile=profile,
        default_includes=["quotes"],
        default_watchlist_tickers=["AAPL"],
    )
    assert sched.consensus is False
