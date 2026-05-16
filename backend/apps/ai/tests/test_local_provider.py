from unittest.mock import MagicMock, patch

import pytest

from apps.ai.providers.local import LocalProvider


def test_local_requires_base_url():
    with pytest.raises(ValueError):
        LocalProvider(api_key="", base_url="")


def test_local_name_is_local():
    p = LocalProvider(api_key="", base_url="http://localhost:11434/v1")
    assert p.name == "local"


@pytest.mark.asyncio
async def test_local_reuses_openai_streaming_shape():
    """LocalProvider.run should behave identically to OpenAIProvider.run when
    given an OpenAI-compatible endpoint. Patch AsyncOpenAI + assert base_url."""
    captured = {}

    class _FakeClient:
        def __init__(self, **kw):
            captured.update(kw)
            self.chat = MagicMock()

            async def create(**kwargs):
                async def gen():
                    chunk = MagicMock()
                    choice = MagicMock()
                    choice.delta.content = "hello"
                    chunk.choices = [choice]
                    chunk.usage = None
                    yield chunk
                    final = MagicMock()
                    final.choices = []
                    final.usage = MagicMock(
                        prompt_tokens=1,
                        completion_tokens=1,
                        prompt_tokens_details=MagicMock(cached_tokens=0),
                    )
                    yield final

                return _AsyncIter(gen())

            self.chat.completions.create = create

    class _AsyncIter:
        def __init__(self, it):
            self._it = it

        def __aiter__(self):
            return self._it

    with patch("apps.ai.providers.openai.AsyncOpenAI", _FakeClient):
        from apps.ai.types import ChatMessage, RunRequest

        p = LocalProvider(api_key="", base_url="http://host.docker.internal:11434/v1")
        req = RunRequest(
            model="llama3", system="x", messages=[ChatMessage(role="user", content="hi")]
        )
        async for _ in p.run(req):
            pass

    assert captured["base_url"].startswith("http://host.docker.internal")
