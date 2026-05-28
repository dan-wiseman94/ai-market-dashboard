import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from apps.ai.providers.openai import OpenAIProvider


def _provider_with_ids(ids):
    p = OpenAIProvider(api_key="x")  # real AsyncOpenAI is constructed then replaced
    client = MagicMock()
    client.with_options.return_value = client
    client.models.list = AsyncMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(id=i) for i in ids])
    )
    p._client = client
    return p, client


def test_list_models_returns_sorted_ids():
    p, client = _provider_with_ids(["mistral", "llama3", "codellama"])
    result = asyncio.run(p.list_models())
    assert result == ["codellama", "llama3", "mistral"]
    client.with_options.assert_called_once_with(timeout=10.0)


def test_list_models_honors_mock_mode(monkeypatch):
    monkeypatch.setattr("apps.core.mocks.is_mock_mode", lambda: True)
    p, client = _provider_with_ids(["ignored"])
    result = asyncio.run(p.list_models())
    assert result == ["local-7b", "local-13b"]
    client.models.list.assert_not_called()
