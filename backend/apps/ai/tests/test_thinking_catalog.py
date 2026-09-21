"""Per-model thinking shape + effort clamping resolve off the catalog.

The wire shapes are mutually exclusive: an adaptive row 400s on `budget_tokens`
and a budget row 400s on both adaptive and `output_config.effort`, so the branch
has to be data, not a hardcoded id list in the provider.
"""

from __future__ import annotations

import pytest

from apps.ai.catalog import (
    DEFAULT_CLAUDE_MODEL,
    THINKING_ADAPTIVE,
    THINKING_BUDGET,
    list_models,
    resolve_effort,
    thinking_style,
)


def test_catalog_default_claude_model_is_adaptive():
    assert thinking_style("claude", DEFAULT_CLAUDE_MODEL) == THINKING_ADAPTIVE


def test_haiku_is_the_only_budget_shaped_claude_row():
    budget_rows = [m.id for m in list_models("claude") if m.thinking == THINKING_BUDGET]
    assert budget_rows == ["claude-haiku-4-5-20251001"]


def test_unknown_model_resolves_to_adaptive():
    # Forward-safe: a model shipped upstream before the catalog caught up takes
    # the adaptive shape, which is what every current Claude row accepts.
    assert thinking_style("claude", "claude-something-new") == THINKING_ADAPTIVE


@pytest.mark.parametrize(
    ("model", "asked", "expected"),
    [
        ("claude-opus-5", "max", "max"),
        ("claude-opus-5", "xhigh", "xhigh"),
        # Sonnet 4.6 predates the xhigh rung; step DOWN, never up.
        ("claude-sonnet-4-6", "xhigh", "high"),
        ("claude-sonnet-4-6", "max", "max"),
        # Haiku rejects the parameter outright.
        ("claude-haiku-4-5-20251001", "high", ""),
        # "" means "omit the parameter" and must stay omitted.
        ("claude-opus-5", "", ""),
        # An unrecognized string falls back to the API's own default.
        ("claude-opus-5", "turbo", "high"),
    ],
)
def test_resolve_effort_clamps_per_model(model, asked, expected):
    assert resolve_effort("claude", model, asked) == expected


def test_openai_rows_take_no_effort():
    assert all(m.effort_levels == () for m in list_models("openai"))
