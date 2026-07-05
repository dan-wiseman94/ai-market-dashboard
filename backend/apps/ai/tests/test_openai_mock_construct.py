"""OpenAI/local providers must be constructible under MOCK_EXTERNAL with no key.

E2E (and any mock run) seeds no api_key; the SDK client demands one at
construction, so without the mock fallback an openai branch dies before run()
can short-circuit.
"""

from __future__ import annotations

import pytest


def test_openai_provider_constructs_without_key_under_mock(monkeypatch):
    monkeypatch.setenv("MOCK_EXTERNAL", "true")
    from apps.ai.providers.openai import OpenAIProvider

    OpenAIProvider(api_key="")  # must not raise
    OpenAIProvider(api_key="", base_url="http://example/v1")


def test_openai_provider_still_requires_key_without_mock(monkeypatch):
    monkeypatch.delenv("MOCK_EXTERNAL", raising=False)
    from apps.ai.providers.openai import OpenAIProvider

    with pytest.raises(Exception):  # noqa: B017 - openai.OpenAIError at construction
        OpenAIProvider(api_key="")
