from apps.ai.catalog import get_model, list_models


def test_openai_models_in_catalog():
    ids = [m.id for m in list_models("openai")]
    assert "gpt-5" in ids
    assert "gpt-5-mini" in ids


def test_openai_pricing_reasonable():
    m = get_model("openai", "gpt-5")
    assert m is not None
    assert m.input_per_mtok > 0
    assert m.output_per_mtok > m.input_per_mtok


def test_local_models_absent_by_default():
    """Local provider catalog is empty — users declare their own model names at runtime."""
    local = list_models("local")
    assert local == []
