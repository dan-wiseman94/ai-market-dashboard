from unittest.mock import patch

import pytest

from apps.ai.providers import get_provider
from apps.ai.providers.local import LocalProvider


def test_get_provider_local():
    with patch("apps.ai.providers.openai.AsyncOpenAI"):
        p = get_provider("local", api_key="", base_url="http://localhost:11434/v1")
    assert isinstance(p, LocalProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("imaginary", api_key="x")
