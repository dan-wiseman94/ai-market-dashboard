"""Observer wiring for the opt-in consensus path.

Mirrors test_structured_outputs.py's patching style: patches run_structured (no
mock-mode short-circuit) and asserts the persisted Message. Also asserts the
consensus=False paths (structured + streaming) are UNCHANGED.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.observer.models import ObserverSchedule
from apps.observer.schemas import ObservationReport, Signal
from apps.observer.services import run as run_service
from apps.observer.services.threads import get_or_create_observer_thread
from apps.profiles.models import TradingProfile
from apps.secrets.models import ProviderConfig
from apps.snapshots.models import Snapshot
from apps.threads.models import Message

pytestmark = pytest.mark.django_db


def _report(bias: str, signals: dict[str, str] | None = None) -> ObservationReport:
    return ObservationReport(
        headline="h",
        bias=bias,  # type: ignore[arg-type]
        summary="s",
        signals=[
            Signal(
                ticker=t,
                bias=b,  # type: ignore[arg-type]
                thesis="t",
                invalidation="i",
                confidence=0.5,
            )
            for t, b in (signals or {}).items()
        ],
        next_check_in="later",
    )


def _profile() -> TradingProfile:
    return TradingProfile.objects.create(
        name="P", style="x", default_provider="claude", default_model="claude-opus-4-8"
    )


def _consensus_schedule(profile) -> ObserverSchedule:
    return ObserverSchedule.objects.create(
        name="consensus-sched",
        profile=profile,
        market_hours_only=False,
        objective_template="watch",
        default_includes=["quotes"],
        default_watchlist_tickers=["SPY"],
        consensus=True,
    )


def test_consensus_fire_persists_consensus_report_message():
    """consensus=True + >=2 structured-capable pairs -> a kind=consensus_report Message."""
    p = _profile()
    sched = _consensus_schedule(p)
    snap = Snapshot.objects.create(
        profile=p,
        objective="watch",
        includes=["quotes"],
        source="observer",
        status="pending",
    )
    pairs = [
        ("claude", "claude-a", "sk-ant", "", None, None),
        ("claude", "claude-b", "sk-ant", "", None, None),
        ("claude", "claude-c", "sk-ant", "", None, None),
    ]
    reports = [
        _report("bullish", {"SPY": "bullish"}),
        _report("bullish", {"SPY": "bullish"}),
        _report("bearish", {"SPY": "bearish"}),
    ]

    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch("apps.observer.services.run.check_daily_cap"),
        patch("apps.observer.services.run.check_monthly_cap"),
        patch("apps.observer.services.run.capture", return_value=snap),
        patch("apps.observer.services.run.serialize_for_ai", return_value="## BODY"),
        patch("apps.observer.services.run.assemble_coach_context", return_value=""),
        patch("apps.observer.services.run.notify"),
        patch.object(run_service.run_ai_on_message, "delay") as streaming,
        patch(
            "apps.observer.services.consensus.structured_capable_pairs",
            return_value=pairs,
        ),
        patch(
            "apps.observer.services.consensus.run_structured",
            side_effect=reports,
        ),
        patch("apps.observer.services.consensus.check_daily_cap"),
        patch("apps.observer.services.consensus.check_monthly_cap"),
    ):
        run_service.run_observer(sched.id)

    # The streaming path must NOT run for a consensus fire.
    streaming.assert_not_called()

    thread = get_or_create_observer_thread(p)
    msg = Message.objects.filter(thread=thread, role="assistant").order_by("-id").first()
    assert msg is not None
    assert msg.content["kind"] == "consensus_report"
    rep = msg.content["report"]
    # Hand-checked aggregation: 3 takes, 2 bullish / 1 bearish.
    assert rep["n_providers"] == 3
    assert rep["modal_bias"] == "bullish"
    assert rep["bias_agreement"] == round(2 / 3, 4)
    assert rep["divergent"] is True
    assert rep["per_ticker"]["SPY"]["modal"] == "bullish"
    assert rep["note"] == ""


def test_consensus_fire_degrades_with_single_provider():
    """One usable provider -> honest degraded consensus_report Message (no fake)."""
    p = _profile()
    sched = _consensus_schedule(p)
    snap = Snapshot.objects.create(
        profile=p,
        objective="watch",
        includes=["quotes"],
        source="observer",
        status="pending",
    )
    pairs = [("claude", "claude-a", "sk-ant", "", None, None)]

    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch("apps.observer.services.run.check_daily_cap"),
        patch("apps.observer.services.run.check_monthly_cap"),
        patch("apps.observer.services.run.capture", return_value=snap),
        patch("apps.observer.services.run.serialize_for_ai", return_value="## BODY"),
        patch("apps.observer.services.run.assemble_coach_context", return_value=""),
        patch("apps.observer.services.run.notify"),
        patch(
            "apps.observer.services.consensus.structured_capable_pairs",
            return_value=pairs,
        ),
        patch(
            "apps.observer.services.consensus.run_structured",
            side_effect=[_report("bullish")],
        ),
        patch("apps.observer.services.consensus.check_daily_cap"),
        patch("apps.observer.services.consensus.check_monthly_cap"),
    ):
        run_service.run_observer(sched.id)

    thread = get_or_create_observer_thread(p)
    msg = Message.objects.filter(thread=thread, role="assistant").order_by("-id").first()
    assert msg is not None
    assert msg.content["kind"] == "consensus_report"
    rep = msg.content["report"]
    assert rep["n_providers"] == 1
    assert rep["bias_agreement"] is None
    assert "single provider" in rep["note"]


def test_consensus_false_uses_structured_path_unchanged():
    """consensus=False + structured=True -> the existing structured_observation path."""
    p = _profile()
    cfg = ProviderConfig.objects.create(provider="claude", enabled=True)
    cfg.api_key = "sk-ant"  # type: ignore[misc]
    cfg.save()
    sched = ObserverSchedule.objects.create(
        name="structured-only",
        profile=p,
        market_hours_only=False,
        objective_template="watch",
        default_includes=["quotes"],
        default_watchlist_tickers=["SPY"],
        structured=True,
        consensus=False,
    )
    snap = Snapshot.objects.create(
        profile=p,
        objective="watch",
        includes=["quotes"],
        source="observer",
        status="pending",
    )

    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch("apps.observer.services.run.check_daily_cap"),
        patch("apps.observer.services.run.check_monthly_cap"),
        patch("apps.observer.services.run.capture", return_value=snap),
        patch("apps.observer.services.run.serialize_for_ai", return_value="## BODY"),
        patch("apps.observer.services.run.assemble_coach_context", return_value=""),
        patch("apps.observer.services.run.notify"),
        patch.object(run_service, "run_structured", return_value=_report("neutral")),
        # If the consensus path were wrongly taken, this would be hit — assert NOT.
        patch("apps.observer.services.consensus.consensus_report") as consensus_fn,
    ):
        run_service.run_observer(sched.id)

    consensus_fn.assert_not_called()
    thread = get_or_create_observer_thread(p)
    msg = Message.objects.filter(thread=thread, role="assistant").order_by("-id").first()
    assert msg is not None
    assert msg.content["kind"] == "structured_observation"


def test_consensus_false_streaming_path_unchanged():
    """consensus=False + structured=False -> the streaming run_ai_on_message path."""
    p = _profile()
    sched = ObserverSchedule.objects.create(
        name="streaming",
        profile=p,
        market_hours_only=False,
        objective_template="watch",
        default_includes=["quotes"],
        default_watchlist_tickers=["SPY"],
        structured=False,
        consensus=False,
    )
    snap = Snapshot.objects.create(
        profile=p,
        objective="watch",
        includes=["quotes"],
        source="observer",
        status="pending",
    )

    with (
        patch("apps.observer.services.run.any_market_open", return_value=True),
        patch("apps.observer.services.run.check_daily_cap"),
        patch("apps.observer.services.run.check_monthly_cap"),
        patch("apps.observer.services.run.capture", return_value=snap),
        patch("apps.observer.services.run.serialize_for_ai", return_value="## BODY"),
        patch("apps.observer.services.run.assemble_coach_context", return_value=""),
        patch("apps.observer.services.run.notify"),
        patch.object(run_service.run_ai_on_message, "delay") as streaming,
        patch("apps.observer.services.consensus.consensus_report") as consensus_fn,
    ):
        run_service.run_observer(sched.id)

    consensus_fn.assert_not_called()
    streaming.assert_called_once()
    # No structured/consensus assistant Message — only the synthetic user turn.
    thread = get_or_create_observer_thread(p)
    assert not Message.objects.filter(thread=thread, role="assistant").exists()
