from apps.ai.catalog import list_models


def test_local_models_absent_by_default():
    """Local provider catalog is empty — users declare their own model names at runtime."""
    local = list_models("local")
    assert local == []
