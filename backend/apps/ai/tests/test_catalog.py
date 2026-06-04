from apps.ai.catalog import KNOWN_PROVIDERS, ceiling_for_provider, get_model, list_models


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


def test_known_providers_contains_claude_openai_local():
    assert "claude" in KNOWN_PROVIDERS
    assert "openai" in KNOWN_PROVIDERS
    assert "local" in KNOWN_PROVIDERS


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
    assert openai_ceiling.id == "gpt-5"
    claude_ceiling = ceiling_for_provider("claude")
    assert claude_ceiling is not None
    assert claude_ceiling.id == "claude-opus-4-8"


def test_ceiling_for_provider_unknown_returns_none():
    assert ceiling_for_provider("nonexistent-provider") is None
