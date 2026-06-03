"""Property-based tests for payload pruning (apps.snapshots.token_budget).

Pure function — no DB.
"""

from hypothesis import given
from hypothesis import strategies as st

from apps.snapshots.token_budget import prune_to_budget

# Keys the pruner knows how to drop (apps.snapshots.token_budget._PRUNE_ORDER).
_PRUNABLE = ["chain", "news", "ohlc", "breadth", "quotes", "positions"]
_sections = st.dictionaries(
    keys=st.sampled_from(_PRUNABLE), values=st.text(max_size=300), max_size=6
)
_budget = st.integers(min_value=0, max_value=100_000)


@given(sections=_sections, budget=_budget)
def test_kept_and_pruned_partition_the_input(sections, budget):
    kept, pruned = prune_to_budget(sections, max_tokens=budget)
    assert set(kept) | set(pruned) == set(sections)
    assert set(kept).isdisjoint(set(pruned))


@given(sections=_sections, budget=_budget)
def test_kept_values_are_unchanged(sections, budget):
    kept, _ = prune_to_budget(sections, max_tokens=budget)
    for key, value in kept.items():
        assert value == sections[key]


@given(sections=_sections)
def test_under_budget_is_returned_unchanged(sections):
    kept, pruned = prune_to_budget(sections, max_tokens=10**9)
    assert kept == sections
    assert pruned == []


@given(sections=_sections, budget=_budget)
def test_pruning_is_idempotent(sections, budget):
    kept1, _ = prune_to_budget(sections, max_tokens=budget)
    kept2, pruned2 = prune_to_budget(kept1, max_tokens=budget)
    assert kept2 == kept1
    assert pruned2 == []
