from apps.ai.catalog import KNOWN_PROVIDERS, get_model, list_models


def test_lists_claude_models():
    models = list_models("claude")
    names = [m.id for m in models]
    assert "claude-opus-4-7" in names
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
