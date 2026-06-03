"""Property-based tests for cost math (apps.ai.cost.cost_usd_for).

Pure function over the catalog — no DB. Invariants a correct pricing fn must hold.
"""

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from apps.ai.cost import cost_usd_for
from apps.ai.types import TokenUsage

_MODEL = ("claude", "claude-sonnet-4-6")
_TOK = st.integers(min_value=0, max_value=5_000_000)
_DELTA = st.integers(min_value=0, max_value=1_000_000)


def test_zero_tokens_zero_cost():
    assert cost_usd_for(*_MODEL, TokenUsage()) == Decimal("0")


@given(inp=_TOK, out=_TOK, cached=_TOK)
def test_local_provider_always_free(inp, out, cached):
    usage = TokenUsage(input_tokens=inp, output_tokens=out, cached_tokens=cached)
    assert cost_usd_for("local", "any-model", usage) == Decimal("0")


@given(inp=_TOK, out=_TOK)
def test_cost_is_non_negative(inp, out):
    assert cost_usd_for(*_MODEL, TokenUsage(input_tokens=inp, output_tokens=out)) >= 0


@given(base=_TOK, extra=_DELTA, out=_TOK)
def test_monotonic_in_input_tokens(base, extra, out):
    lo = cost_usd_for(*_MODEL, TokenUsage(input_tokens=base, output_tokens=out))
    hi = cost_usd_for(*_MODEL, TokenUsage(input_tokens=base + extra, output_tokens=out))
    assert lo <= hi


@given(inp=_TOK, base=_TOK, extra=_DELTA)
def test_monotonic_in_output_tokens(inp, base, extra):
    lo = cost_usd_for(*_MODEL, TokenUsage(input_tokens=inp, output_tokens=base))
    hi = cost_usd_for(*_MODEL, TokenUsage(input_tokens=inp, output_tokens=base + extra))
    assert lo <= hi
