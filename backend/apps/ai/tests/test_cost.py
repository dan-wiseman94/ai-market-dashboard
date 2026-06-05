from decimal import Decimal

import pytest

from apps.ai.cost import cost_usd_for
from apps.ai.types import TokenUsage


def test_cost_basic_sonnet():
    usage = TokenUsage(input_tokens=10_000, output_tokens=5_000)
    cost = cost_usd_for("claude", "claude-sonnet-4-6", usage)
    assert cost == pytest.approx(Decimal("0.1050"), abs=Decimal("0.0001"))


def test_cost_counts_cached_tokens_cheaper():
    usage = TokenUsage(input_tokens=10_000, output_tokens=5_000, cached_tokens=2_000)
    cost = cost_usd_for("claude", "claude-sonnet-4-6", usage)
    assert cost == pytest.approx(Decimal("0.09975"), abs=Decimal("0.0001"))


def test_cost_for_unknown_model_uses_provider_ceiling():
    usage = TokenUsage(input_tokens=1000, output_tokens=1000)
    cost = cost_usd_for("claude", "claude-made-up-model", usage)
    assert cost > Decimal("0.08")


def test_cost_local_provider_is_zero():
    usage = TokenUsage(input_tokens=100_000, output_tokens=50_000)
    assert cost_usd_for("local", "anything", usage) == Decimal("0")


def test_cost_unknown_provider_with_no_catalog_entries_is_zero():
    # Provider isn't "local" and has no catalog models, so both get_model and the
    # provider ceiling are None — cost must fall through to zero, not raise.
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost_usd_for("nonexistent-provider", "whatever", usage) == Decimal("0")


def test_cost_unknown_model_prices_off_provider_ceiling_not_global_max():
    # openai's ceiling is gpt-5 ($5 in / $40 out per Mtok); the global priciest
    # model is claude-opus ($15 / $75). An unknown openai model must be priced off
    # openai's own ceiling, not whichever model tops the whole catalog.
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = cost_usd_for("openai", "made-up-openai-model", usage)
    assert cost == Decimal("45.000000")
