import pytest

from apps.ai.catalog import (
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_OPENAI_MODEL,
    catalog_owner,
    ceiling_for_provider,
    default_model_for,
    foreign_model_error,
    get_model,
    is_foreign_model,
    list_models,
)


def test_lists_claude_models():
    models = list_models("claude")
    names = [m.id for m in models]
    assert "claude-opus-4-8" in names
    assert "claude-sonnet-4-6" in names
    assert "claude-haiku-4-5-20251001" in names


def test_get_model_returns_pricing():
    m = get_model("claude", "claude-sonnet-4-6")
    assert m is not None
    assert m.provider == "claude"
    assert m.input_per_mtok > 0
    assert m.output_per_mtok > m.input_per_mtok
    assert m.supports_vision is True


def test_get_model_unknown_returns_none():
    assert get_model("claude", "imaginary-model") is None


def test_list_models_without_provider_returns_full_catalog():
    models = list_models()
    providers = {m.provider for m in models}
    assert "claude" in providers
    assert "openai" in providers
    assert len(models) >= 6


def test_ceiling_for_provider_is_scoped_to_that_provider():
    # The priciest-by-output model *within* the provider, not the global max.
    openai_ceiling = ceiling_for_provider("openai")
    assert openai_ceiling is not None
    assert openai_ceiling.provider == "openai"
    assert openai_ceiling.id == "gpt-6-astra"
    claude_ceiling = ceiling_for_provider("claude")
    assert claude_ceiling is not None
    assert claude_ceiling.id == "claude-fable-5-1"


def test_ceiling_for_provider_unknown_returns_none():
    assert ceiling_for_provider("nonexistent-provider") is None


def test_current_generation_models_present():
    claude_ids = {m.id for m in list_models("claude")}
    assert {"claude-fable-5-1", "claude-opus-5", "claude-sonnet-5"} <= claude_ids
    openai_ids = {m.id for m in list_models("openai")}
    assert {"gpt-6-astra", "gpt-5.6-sol"} <= openai_ids


@pytest.mark.parametrize(
    ("provider", "model_id", "inp", "cached", "out", "ctx"),
    [
        ("claude", "claude-fable-5-1", 10.00, 0.25, 50.00, 1_000_000),
        ("claude", "claude-opus-5", 5.00, 0.50, 25.00, 1_000_000),
        ("claude", "claude-sonnet-5", 2.00, 0.20, 10.00, 1_000_000),
        ("claude", "claude-opus-4-8", 5.00, 0.50, 25.00, 1_000_000),
        ("claude", "claude-sonnet-4-6", 3.00, 0.375, 15.00, 1_000_000),
        ("openai", "gpt-6-astra", 10.00, 1.00, 50.00, 1_050_000),
        ("openai", "gpt-5.6-sol", 4.00, 0.40, 20.00, 1_050_000),
        ("openai", "gpt-5", 1.25, 0.125, 10.00, 400_000),
        ("openai", "gpt-5-mini", 0.25, 0.025, 2.00, 400_000),
        ("openai", "gpt-5-nano", 0.05, 0.005, 0.40, 400_000),
    ],
)
def test_verified_pricing_and_context(provider, model_id, inp, cached, out, ctx):
    m = get_model(provider, model_id)
    assert m is not None
    assert (m.input_per_mtok, m.cached_per_mtok, m.output_per_mtok, m.context_window) == (
        inp,
        cached,
        out,
        ctx,
    )


def test_default_model_for_each_provider():
    assert DEFAULT_CLAUDE_MODEL == "claude-opus-5"
    assert DEFAULT_OPENAI_MODEL == "gpt-5.6-sol"
    assert default_model_for("claude") == "claude-opus-5"
    assert default_model_for("anthropic") == "claude-opus-5"
    assert default_model_for("openai") == "gpt-5.6-sol"
    assert default_model_for("local") == ""
    assert default_model_for("nonexistent") == ""


def test_defaults_are_catalog_rows():
    assert get_model("claude", DEFAULT_CLAUDE_MODEL) is not None
    assert get_model("openai", DEFAULT_OPENAI_MODEL) is not None


def test_catalog_owner_maps_ids_to_provider():
    assert catalog_owner("claude-opus-5") == "claude"
    assert catalog_owner("gpt-5.6-sol") == "openai"
    assert catalog_owner("llama-3.1-70b") is None


@pytest.mark.parametrize(
    ("provider", "model", "foreign"),
    [
        ("claude", "claude-opus-5", False),
        ("anthropic", "claude-opus-5", False),
        ("claude", "gpt-5.6-sol", True),
        ("openai", "claude-sonnet-5", True),
        ("local", "llama-3.1-70b", False),
        ("local", "gpt-5", True),
        ("openai", "", False),
    ],
)
def test_is_foreign_model(provider, model, foreign):
    assert is_foreign_model(provider, model) is foreign


def test_foreign_model_error_names_owner():
    assert foreign_model_error("claude", "claude-opus-5") is None
    msg = foreign_model_error("claude", "gpt-5.6-sol")
    assert msg == "gpt-5.6-sol is an openai catalog model; pick a claude model or clear the field."
