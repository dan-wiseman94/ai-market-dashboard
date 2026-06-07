"""consensus_report cross-model agreement service.

run_structured has no mock-mode short-circuit, so we patch it directly (the repo
pattern, mirroring apps/observer/tests/test_structured_outputs.py).
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest

from apps.observer.schemas import ConsensusReport, ObservationReport, Signal
from apps.observer.services.consensus import StructuredPair
from apps.secrets.models import ProviderConfig

pytestmark = pytest.mark.django_db


def _report(bias: str, signals: dict[str, str] | None = None) -> ObservationReport:
    sigs = [
        Signal(
            ticker=t,
            bias=b,  # type: ignore[arg-type]
            thesis="t",
            invalidation="i",
            confidence=0.5,
        )
        for t, b in (signals or {}).items()
    ]
    return ObservationReport(
        headline="h",
        bias=bias,  # type: ignore[arg-type]
        summary="s",
        signals=sigs,
        next_check_in="later",
    )


def _pairs(n: int) -> list[StructuredPair]:
    """n structured-capable pairs.

    Mirrors ``structured_capable_pairs()``'s ``StructuredPair`` shape. Caps are
    Infinity/None so the cap checks are no-ops unless a test patches them.

    Note: ``ProviderConfig.provider`` is unique, so the only real Claude-family
    provider string is ``"claude"``. To exercise the N-take aggregation math we
    patch ``structured_capable_pairs`` to return several ``claude`` pairs that
    differ by model — the aggregation keys takes by ``provider/model``.
    """
    return [
        StructuredPair(
            provider="claude",
            model=f"claude-model-{i}",
            api_key="sk-ant-x",
            base_url="",
            daily_cap=Decimal("Infinity"),
            monthly_cap=None,
        )
        for i in range(n)
    ]


def test_three_takes_agreement_math():
    """3 pairs -> bullish/bullish/bearish: modal=bullish, agreement=2/3, divergent."""
    pairs = _pairs(3)
    reports = [
        _report("bullish", {"AAPL": "bullish"}),
        _report("bullish", {"AAPL": "bullish"}),
        _report("bearish", {"AAPL": "bearish"}),
    ]
    with (
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
        from apps.observer.services.consensus import consensus_report

        result = consensus_report(system="sys", user="usr")

    assert isinstance(result, ConsensusReport)
    assert result.n_providers == 3
    assert result.modal_bias == "bullish"
    assert result.bias_agreement == round(2 / 3, 4)  # 0.6667
    assert result.divergent is True
    # Per-ticker: AAPL appears in all 3 takes; 2 bullish, 1 bearish.
    aapl = result.per_ticker["AAPL"]
    assert aapl["modal"] == "bullish"
    assert aapl["agreement"] == round(2 / 3, 4)
    assert aapl["takes"] == {
        "claude/claude-model-0": "bullish",
        "claude/claude-model-1": "bullish",
        "claude/claude-model-2": "bearish",
    }
    assert len(result.takes) == 3
    assert result.note == ""


def test_unanimous_not_divergent():
    """All-agree -> agreement 1.0, divergent False."""
    pairs = _pairs(2)
    reports = [_report("bearish"), _report("bearish")]
    with (
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
        from apps.observer.services.consensus import consensus_report

        result = consensus_report(system="sys", user="usr")

    assert result.n_providers == 2
    assert result.modal_bias == "bearish"
    assert result.bias_agreement == 1.0
    assert result.divergent is False


def test_single_provider_degrades_honestly():
    """<2 usable pairs -> degraded result; no fabricated consensus."""
    pairs = _pairs(1)
    with (
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
        from apps.observer.services.consensus import consensus_report

        result = consensus_report(system="sys", user="usr")

    assert result.n_providers == 1
    assert result.bias_agreement is None
    assert result.modal_bias == "bullish"  # the lone take's bias, honestly reported
    assert result.divergent is False
    assert "single provider" in result.note
    assert result.per_ticker == {}


def test_zero_pairs_degrades_to_empty():
    """No structured-capable providers at all -> n=0, None agreement, note set."""
    with (
        patch(
            "apps.observer.services.consensus.structured_capable_pairs",
            return_value=[],
        ),
        patch("apps.observer.services.consensus.run_structured") as mock_run,
    ):
        from apps.observer.services.consensus import consensus_report

        result = consensus_report(system="sys", user="usr")

    mock_run.assert_not_called()
    assert result.n_providers == 0
    assert result.bias_agreement is None
    assert result.modal_bias is None
    assert result.divergent is False
    assert "single provider" in result.note or "no consensus" in result.note


def test_error_pair_is_skipped_not_raised():
    """A pair whose run_structured raises is skipped + counted out; no crash.

    3 pairs, middle one raises -> 2 survivors (bullish, bearish) -> divergent,
    agreement 1/2, n_providers reflects survivors only.
    """
    pairs = _pairs(3)
    side = [_report("bullish"), RuntimeError("boom"), _report("bearish")]
    with (
        patch(
            "apps.observer.services.consensus.structured_capable_pairs",
            return_value=pairs,
        ),
        patch(
            "apps.observer.services.consensus.run_structured",
            side_effect=side,
        ),
        patch("apps.observer.services.consensus.check_daily_cap"),
        patch("apps.observer.services.consensus.check_monthly_cap"),
    ):
        from apps.observer.services.consensus import consensus_report

        result = consensus_report(system="sys", user="usr")

    assert result.n_providers == 2  # survivors only
    assert result.bias_agreement == 0.5
    assert result.divergent is True
    assert sorted(t.bias for t in result.takes) == ["bearish", "bullish"]


def test_capped_provider_is_skipped():
    """A provider over its cost cap is skipped before run_structured — counted out."""
    from apps.ai.cost import CostCapExceededError

    pairs = _pairs(2)
    # First model's daily check passes; second raises -> skipped before run.
    daily_side = [None, CostCapExceededError("daily cap exceeded")]
    with (
        patch(
            "apps.observer.services.consensus.structured_capable_pairs",
            return_value=pairs,
        ),
        patch(
            "apps.observer.services.consensus.run_structured",
            side_effect=[_report("bullish")],
        ),
        patch(
            "apps.observer.services.consensus.check_daily_cap",
            side_effect=daily_side,
        ),
        patch("apps.observer.services.consensus.check_monthly_cap"),
    ):
        from apps.observer.services.consensus import consensus_report

        result = consensus_report(system="sys", user="usr")

    # One provider survived (the capped one was skipped before run_structured).
    assert result.n_providers == 1
    assert result.modal_bias == "bullish"
    assert result.bias_agreement is None  # degraded — only 1 usable
    assert "single provider" in result.note


def test_consensus_report_never_raises_on_all_errors():
    """Every pair erroring -> empty/degraded result, not an exception."""
    pairs = _pairs(2)
    with (
        patch(
            "apps.observer.services.consensus.structured_capable_pairs",
            return_value=pairs,
        ),
        patch(
            "apps.observer.services.consensus.run_structured",
            side_effect=[RuntimeError("a"), RuntimeError("b")],
        ),
        patch("apps.observer.services.consensus.check_daily_cap"),
        patch("apps.observer.services.consensus.check_monthly_cap"),
    ):
        from apps.observer.services.consensus import consensus_report

        result = consensus_report(system="sys", user="usr")

    assert result.n_providers == 0
    assert result.bias_agreement is None
    assert result.modal_bias is None


# --- structured_capable_pairs selection (hits the real DB query) -------------


def test_structured_capable_pairs_selects_claude_family_only():
    """Only enabled Claude-family configs with a key are selected."""
    claude = ProviderConfig.objects.create(provider="claude", default_model="claude-opus-4-8")
    claude.api_key = "sk-ant-1"  # type: ignore[misc]
    claude.save()
    # OpenAI, enabled, keyed -> NOT structured-capable (Claude-only).
    openai = ProviderConfig.objects.create(provider="openai", default_model="gpt-5")
    openai.api_key = "sk-oai"  # type: ignore[misc]
    openai.save()
    # Local, enabled -> NOT structured-capable.
    ProviderConfig.objects.create(provider="local", default_model="llama")

    from apps.observer.services.consensus import structured_capable_pairs

    pairs = structured_capable_pairs()
    providers = {p[0] for p in pairs}
    assert providers == {"claude"}
    assert pairs[0][0] == "claude"
    assert pairs[0][1] == "claude-opus-4-8"
    assert pairs[0][2] == "sk-ant-1"


def test_structured_capable_pairs_skips_disabled():
    """Disabled claude config is excluded even with a key."""
    c = ProviderConfig.objects.create(provider="claude", default_model="m", enabled=False)
    c.api_key = "sk-ant"  # type: ignore[misc]
    c.save()
    from apps.observer.services.consensus import structured_capable_pairs

    assert structured_capable_pairs() == []


def test_structured_capable_pairs_skips_keyless_enabled():
    """Enabled claude config with no key -> excluded (would no-op anyway)."""
    ProviderConfig.objects.create(provider="claude", default_model="m", enabled=True)
    from apps.observer.services.consensus import structured_capable_pairs

    assert structured_capable_pairs() == []
