from unittest.mock import patch

import pytest

from apps.ai.providers import get_provider
from apps.ai.providers.claude import ClaudeProvider
from apps.ai.providers.local import LocalProvider
from apps.ai.providers.openai import OpenAIProvider


def test_get_provider_claude():
    with patch("apps.ai.providers.claude.AsyncAnthropic"):
        p = get_provider("claude", api_key="sk-ant-x")
    assert isinstance(p, ClaudeProvider)


def test_get_provider_openai():
    with patch("apps.ai.providers.openai.AsyncOpenAI"):
        p = get_provider("openai", api_key="sk-oai-x")
    assert isinstance(p, OpenAIProvider)
    # Must not be the Local subclass
    assert not isinstance(p, LocalProvider)


def test_get_provider_local():
    with patch("apps.ai.providers.openai.AsyncOpenAI"):
        p = get_provider("local", api_key="", base_url="http://localhost:11434/v1")
    assert isinstance(p, LocalProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("imaginary", api_key="x")
